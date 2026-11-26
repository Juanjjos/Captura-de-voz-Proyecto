#include <string.h>
#include <inttypes.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/stream_buffer.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "esp_bt.h"
#include "esp_bt_main.h"
#include "esp_bt_device.h"
#include "esp_gap_bt_api.h"
#include "esp_hf_client_api.h"
#include "driver/i2s_std.h"
#include "driver/gpio.h"
#include "filtro_ruido.h"

#define NOMBRE_BT            "MicESP32"
#define USAR_DOS_MICROFONOS  true
#define PIN_SCK              GPIO_NUM_26
#define PIN_WS               GPIO_NUM_25
#define PIN_SD               GPIO_NUM_33
#define PIN_BOTON            GPIO_NUM_0
#define PIN_LED              GPIO_NUM_2
#define BLOQUE               256

static const char *TAG = "MIC_BT";

static i2s_chan_handle_t rx;
static StreamBufferHandle_t cola_audio;
static volatile bool audio_conectado = false;
static volatile bool filtro_activo = true;
static volatile int frecuencia_bt = 8000;

static int32_t crudo[BLOQUE * 2];
static float m1[BLOQUE], m2[BLOQUE], filtrada[BLOQUE], original[BLOQUE];
static int16_t salida[BLOQUE];
static fr_estado_t estado;
static fr_biquad_t filtro_bajada_8k;
static portMUX_TYPE metricas_mux = portMUX_INITIALIZER_UNLOCKED;

typedef struct {
  uint64_t i2s_muestras;
  uint64_t i2s_errores;
  uint64_t clip_m1;
  uint64_t clip_m2;
  uint64_t clip_salida;
  uint64_t muestras_salida;
  uint64_t cola_perdida_bytes;
  uint64_t hfp_solicitado_bytes;
  uint64_t hfp_silencio_bytes;
  uint64_t hfp_audio_conexiones;
  uint64_t hfp_audio_desconexiones;
} metricas_t;

static metricas_t metricas;

static int16_t a_pcm16(float muestra, uint64_t *saturadas) {
  float escalada = muestra * 32767.0f;
  if (escalada >= 32767.0f) {
    (*saturadas)++;
    escalada = 32767.0f;
  } else if (escalada <= -32768.0f) {
    (*saturadas)++;
    escalada = -32768.0f;
  }
  return (int16_t)escalada;
}

static void registrar_lectura_i2s(uint64_t muestras, uint64_t clip_m1,
                                  uint64_t clip_m2) {
  portENTER_CRITICAL(&metricas_mux);
  metricas.i2s_muestras += muestras;
  metricas.clip_m1 += clip_m1;
  metricas.clip_m2 += clip_m2;
  portEXIT_CRITICAL(&metricas_mux);
}

static void registrar_salida(uint64_t muestras, uint64_t clip,
                             uint64_t bytes_perdidos) {
  portENTER_CRITICAL(&metricas_mux);
  metricas.muestras_salida += muestras;
  metricas.clip_salida += clip;
  metricas.cola_perdida_bytes += bytes_perdidos;
  portEXIT_CRITICAL(&metricas_mux);
}

static void registrar_lectura_i2s_fallida(void) {
  portENTER_CRITICAL(&metricas_mux);
  metricas.i2s_errores++;
  portEXIT_CRITICAL(&metricas_mux);
}

static void registrar_solicitud_hfp(size_t solicitados, size_t rellenados) {
  portENTER_CRITICAL(&metricas_mux);
  metricas.hfp_solicitado_bytes += solicitados;
  metricas.hfp_silencio_bytes += rellenados;
  portEXIT_CRITICAL(&metricas_mux);
}

static metricas_t obtener_metricas(void) {
  metricas_t copia;
  portENTER_CRITICAL(&metricas_mux);
  copia = metricas;
  portEXIT_CRITICAL(&metricas_mux);
  return copia;
}

static void datos_entrantes(const uint8_t *buf, uint32_t len) {
  (void)buf; (void)len;   // audio del PC hacia el ESP32: no se usa
}

static uint32_t datos_salientes(uint8_t *buf, uint32_t len) {
  size_t n = xStreamBufferReceive(cola_audio, buf, len, 0);
  if (n < len) memset(buf + n, 0, len - n);
  registrar_solicitud_hfp(len, len - n);
  return len;
}

static void evento_hf(esp_hf_client_cb_event_t evento, esp_hf_client_cb_param_t *p) {
  switch (evento) {
    case ESP_HF_CLIENT_CONNECTION_STATE_EVT:
      if (p->conn_stat.state == ESP_HF_CLIENT_CONNECTION_STATE_SLC_CONNECTED) {
        ESP_LOGI(TAG, "Conectado al PC como manos libres");
      } else if (p->conn_stat.state == ESP_HF_CLIENT_CONNECTION_STATE_DISCONNECTED) {
        ESP_LOGI(TAG, "Desconectado del PC");
        audio_conectado = false;
        esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
      }
      break;
    case ESP_HF_CLIENT_AUDIO_STATE_EVT:
      if (p->audio_stat.state == ESP_HF_CLIENT_AUDIO_STATE_CONNECTED ||
          p->audio_stat.state == ESP_HF_CLIENT_AUDIO_STATE_CONNECTED_MSBC) {
        frecuencia_bt = (p->audio_stat.state == ESP_HF_CLIENT_AUDIO_STATE_CONNECTED_MSBC) ? 16000 : 8000;
        ESP_ERROR_CHECK(esp_hf_client_register_data_callback(datos_entrantes, datos_salientes));
        xStreamBufferReset(cola_audio);
        portENTER_CRITICAL(&metricas_mux);
        metricas.hfp_audio_conexiones++;
        portEXIT_CRITICAL(&metricas_mux);
        audio_conectado = true;
        ESP_LOGI(TAG, "Audio abierto a %d Hz", frecuencia_bt);
      } else if (p->audio_stat.state == ESP_HF_CLIENT_AUDIO_STATE_DISCONNECTED) {
        portENTER_CRITICAL(&metricas_mux);
        metricas.hfp_audio_desconexiones++;
        portEXIT_CRITICAL(&metricas_mux);
        audio_conectado = false;
        ESP_LOGI(TAG, "Audio cerrado");
      }
      break;
    default:
      break;
  }
}

static void evento_gap(esp_bt_gap_cb_event_t evento, esp_bt_gap_cb_param_t *p) {
  switch (evento) {
    case ESP_BT_GAP_AUTH_CMPL_EVT:
      if (p->auth_cmpl.stat == ESP_BT_STATUS_SUCCESS) {
        ESP_LOGI(TAG, "Emparejado con: %s", p->auth_cmpl.device_name);
      } else {
        ESP_LOGE(TAG, "Fallo el emparejamiento (%d)", p->auth_cmpl.stat);
      }
      break;
    case ESP_BT_GAP_CFM_REQ_EVT:
      esp_bt_gap_ssp_confirm_reply(p->cfm_req.bda, true);
      break;
    case ESP_BT_GAP_PIN_REQ_EVT: {
      esp_bt_pin_code_t pin = {'1', '2', '3', '4'};
      esp_bt_gap_pin_reply(p->pin_req.bda, true, 4, pin);
      break;
    }
    default:
      break;
  }
}

static void tarea_envio(void *arg) {
  (void)arg;
  while (1) {
    if (audio_conectado) esp_hf_client_outgoing_data_ready();
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

static void iniciar_i2s(void) {
  i2s_chan_config_t canal = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  ESP_ERROR_CHECK(i2s_new_channel(&canal, NULL, &rx));
  i2s_std_config_t cfg = {
    .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(16000),
    .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
    .gpio_cfg = {
      .mclk = I2S_GPIO_UNUSED,
      .bclk = PIN_SCK,
      .ws   = PIN_WS,
      .dout = I2S_GPIO_UNUSED,
      .din  = PIN_SD,
      .invert_flags = { .mclk_inv = false, .bclk_inv = false, .ws_inv = false },
    },
  };
  ESP_ERROR_CHECK(i2s_channel_init_std_mode(rx, &cfg));
  ESP_ERROR_CHECK(i2s_channel_enable(rx));
}

static void tarea_audio(void *arg) {
  (void)arg;
  fr_iniciar(&estado, USAR_DOS_MICROFONOS);
  fr_biquad_iniciar(&filtro_bajada_8k, 1, 3400.0f, FR_FS);
  int boton_antes = 1;
  int64_t ultimo_cambio_boton = 0;
  int64_t siguiente_reporte = esp_timer_get_time() + 1000000;

  while (1) {
    size_t bytes = 0;
    esp_err_t lectura = i2s_channel_read(rx, crudo, sizeof(crudo), &bytes, portMAX_DELAY);
    if (lectura != ESP_OK) {
      registrar_lectura_i2s_fallida();
      continue;
    }
    int n = bytes / 8;
    if (n == 0) continue;
    uint64_t clip_m1 = 0, clip_m2 = 0;
    int pico1 = 0, pico2 = 0;
    for (int i = 0; i < n; i++) {
      int32_t muestra1 = crudo[2 * i] >> 8;
      int32_t muestra2 = crudo[2 * i + 1] >> 8;
      int32_t abs1 = muestra1 < 0 ? -muestra1 : muestra1;
      int32_t abs2 = muestra2 < 0 ? -muestra2 : muestra2;
      if (abs1 > pico1) pico1 = abs1;
      if (abs2 > pico2) pico2 = abs2;
      if (abs1 >= 8380000) clip_m1++;
      if (abs2 >= 8380000) clip_m2++;
      m1[i] = muestra1 / 8388608.0f;
      m2[i] = muestra2 / 8388608.0f;
    }
    registrar_lectura_i2s(n, clip_m1, clip_m2);

    fr_procesar(&estado, m1, USAR_DOS_MICROFONOS ? m2 : NULL, filtrada, original, n);

    int boton = gpio_get_level(PIN_BOTON);
    int64_t tiempo_boton = esp_timer_get_time();
    if (boton == 0 && boton_antes == 1 &&
        tiempo_boton - ultimo_cambio_boton >= 200000) {
      filtro_activo = !filtro_activo;
      gpio_set_level(PIN_LED, filtro_activo);
      ESP_LOGI(TAG, "Filtro %s", filtro_activo ? "ACTIVADO" : "DESACTIVADO");
      ultimo_cambio_boton = tiempo_boton;
    }
    boton_antes = boton;

    if (audio_conectado) {
      const float *fuente = filtro_activo ? filtrada : original;
      bool reducir_a_8k = frecuencia_bt == 8000;
      int k = 0;
      uint64_t clip_salida = 0;
      for (int i = 0; i < n; i++) {
        float filtrada_8k = fr_biquad(&filtro_bajada_8k, fuente[i]);
        if (!reducir_a_8k || (i % 2) == 0) {
          salida[k++] = a_pcm16(reducir_a_8k ? filtrada_8k : fuente[i],
                                &clip_salida);
        }
      }
      size_t bytes_salida = k * sizeof(int16_t);
      size_t enviados = xStreamBufferSend(cola_audio, salida, bytes_salida, 0);
      registrar_salida(k, clip_salida, bytes_salida - enviados);
    }

    int64_t ahora = esp_timer_get_time();
    if (ahora >= siguiente_reporte) {
      metricas_t m = obtener_metricas();
      float clip1_pct = m.i2s_muestras ?
          100.0f * m.clip_m1 / m.i2s_muestras : 0.0f;
      float clip2_pct = m.i2s_muestras ?
          100.0f * m.clip_m2 / m.i2s_muestras : 0.0f;
      float clip_salida_pct = m.muestras_salida ?
          100.0f * m.clip_salida / m.muestras_salida : 0.0f;
      ESP_LOGI(TAG,
               "METRICAS t_ms=%" PRId64 " conectado=%d fs_bt=%d i2s_muestras=%" PRIu64
               " i2s_errores=%" PRIu64 " clip_m1=%" PRIu64 " clip_m2=%" PRIu64
               " clip_salida=%" PRIu64 " muestras_salida=%" PRIu64
               " cola_perdida_bytes=%" PRIu64 " hfp_solicitado_bytes=%" PRIu64
               " hfp_silencio_bytes=%" PRIu64 " hfp_audio_conexiones=%" PRIu64
               " hfp_audio_desconexiones=%" PRIu64
               " clip_m1_pct=%.5f clip_m2_pct=%.5f"
               " clip_salida_pct=%.5f m1_rms=%.5f m2_rms=%.5f relacion=%.3f"
               " piso=%.5f pico1=%d pico2=%d calibracion_muestras=%d voz=%d filtro=%d",
               ahora / 1000, audio_conectado ? 1 : 0, frecuencia_bt,
               m.i2s_muestras, m.i2s_errores, m.clip_m1, m.clip_m2,
               m.clip_salida, m.muestras_salida, m.cola_perdida_bytes,
               m.hfp_solicitado_bytes, m.hfp_silencio_bytes,
               m.hfp_audio_conexiones, m.hfp_audio_desconexiones,
               clip1_pct, clip2_pct,
               clip_salida_pct, estado.rms1, estado.rms2, estado.relacion,
               estado.piso, pico1, pico2, estado.muestras_calibracion,
               estado.voz ? 1 : 0,
               filtro_activo ? 1 : 0);
      siguiente_reporte = ahora + 1000000;
    }
  }
}

void app_main(void) {
  esp_err_t err = nvs_flash_init();
  if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    ESP_ERROR_CHECK(nvs_flash_erase());
    err = nvs_flash_init();
  }
  ESP_ERROR_CHECK(err);

  gpio_reset_pin(PIN_LED);
  gpio_set_direction(PIN_LED, GPIO_MODE_OUTPUT);
  gpio_set_level(PIN_LED, filtro_activo);
  gpio_reset_pin(PIN_BOTON);
  gpio_set_direction(PIN_BOTON, GPIO_MODE_INPUT);
  gpio_set_pull_mode(PIN_BOTON, GPIO_PULLUP_ONLY);

  cola_audio = xStreamBufferCreate(4096, 1);
  if (cola_audio == NULL) {
    ESP_LOGE(TAG, "No se pudo crear la cola de audio");
    return;
  }
  iniciar_i2s();

  ESP_ERROR_CHECK(esp_bt_controller_mem_release(ESP_BT_MODE_BLE));
  esp_bt_controller_config_t bt_cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
  ESP_ERROR_CHECK(esp_bt_controller_init(&bt_cfg));
  ESP_ERROR_CHECK(esp_bt_controller_enable(ESP_BT_MODE_CLASSIC_BT));
  ESP_ERROR_CHECK(esp_bluedroid_init());
  ESP_ERROR_CHECK(esp_bluedroid_enable());

  ESP_ERROR_CHECK(esp_bt_gap_register_callback(evento_gap));
  ESP_ERROR_CHECK(esp_bt_gap_set_device_name(NOMBRE_BT));

  esp_bt_cod_t cod = {0};
  cod.major = ESP_BT_COD_MAJOR_DEV_AV;
  cod.minor = 0x02;
  cod.service = ESP_BT_COD_SRVC_AUDIO;
  ESP_ERROR_CHECK(esp_bt_gap_set_cod(cod, ESP_BT_SET_COD_ALL));

  esp_bt_io_cap_t iocap = ESP_BT_IO_CAP_NONE;
  ESP_ERROR_CHECK(esp_bt_gap_set_security_param(ESP_BT_SP_IOCAP_MODE, &iocap, sizeof(uint8_t)));
  esp_bt_pin_code_t pin = {0};
  ESP_ERROR_CHECK(esp_bt_gap_set_pin(ESP_BT_PIN_TYPE_VARIABLE, 0, pin));

  ESP_ERROR_CHECK(esp_hf_client_register_callback(evento_hf));
  ESP_ERROR_CHECK(esp_hf_client_init());

  ESP_ERROR_CHECK(esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE));
  ESP_LOGI(TAG, "Listo. Busca \"%s\" en el Bluetooth del PC", NOMBRE_BT);

  int num = esp_bt_gap_get_bond_device_num();
  if (num > 0) {
    esp_bd_addr_t lista[num];
    ESP_ERROR_CHECK(esp_bt_gap_get_bond_device_list(&num, lista));
    ESP_LOGI(TAG, "Reconectando al ultimo equipo emparejado...");
    ESP_ERROR_CHECK(esp_hf_client_connect(lista[0]));
  }

  BaseType_t audio_ok = xTaskCreatePinnedToCore(tarea_audio, "audio", 4096, NULL, 5, NULL, 1);
  BaseType_t envio_ok = xTaskCreate(tarea_envio, "envio", 3072, NULL, 5, NULL);
  if (audio_ok != pdPASS || envio_ok != pdPASS) {
    ESP_LOGE(TAG, "No se pudieron iniciar las tareas de audio y Bluetooth");
  }
}
