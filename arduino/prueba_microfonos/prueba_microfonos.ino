#include <ESP_I2S.h>
#include <math.h>
#include "filtro_ruido.h"

const int PIN_SCK = 26;   // D26 -> SCK
const int PIN_WS  = 25;   // D25 -> WS
const int PIN_SD  = 33;   // D33 -> SD
const uint32_t FRECUENCIA = 16000;
const int MUESTRAS = 512;

I2SClass i2s;
int32_t buffer[MUESTRAS * 2];       // izq, der, izq, der...
float m1[MUESTRAS], m2[MUESTRAS], filtrada[MUESTRAS], original[MUESTRAS];
fr_estado_t estado;

void setup() {
  Serial.begin(115200);
  delay(1000);
  i2s.setPins(PIN_SCK, PIN_WS, -1, PIN_SD);
  if (!i2s.begin(I2S_MODE_STD, FRECUENCIA, I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO)) {
    Serial.println("ERROR: no se pudo iniciar I2S.");
    while (true) delay(1000);
  }
  fr_iniciar(&estado, true);
}

void loop() {
  size_t bytesLeidos = i2s.readBytes((char *)buffer, sizeof(buffer));
  int pares = bytesLeidos / 8;
  if (pares == 0) return;

  double suma1 = 0, suma2 = 0;
  int pico1 = 0, pico2 = 0;
  for (int i = 0; i < pares; i++) {
    int32_t v1 = buffer[2 * i] >> 8;
    int32_t v2 = buffer[2 * i + 1] >> 8;
    suma1 += v1;       // Mic 1 (izquierdo)
    suma2 += v2;       // Mic 2 (derecho)
    if (abs(v1) > pico1) pico1 = abs(v1);
    if (abs(v2) > pico2) pico2 = abs(v2);
    m1[i] = v1 / 8388608.0f;
    m2[i] = v2 / 8388608.0f;
  }
  double media1 = suma1 / pares, media2 = suma2 / pares;

  double energia1 = 0, energia2 = 0;
  for (int i = 0; i < pares; i++) {
    double v1 = (buffer[2 * i] >> 8) - media1;
    double v2 = (buffer[2 * i + 1] >> 8) - media2;
    energia1 += v1 * v1;
    energia2 += v2 * v2;
  }
  fr_procesar(&estado, m1, m2, filtrada, original, pares);

  Serial.printf(
    "Mic1_voz:%0.0f,Mic2_ruido:%0.0f,Relacion:%0.2f,Piso:%0.3f,Estado:%s,Pico1:%d,Pico2:%d\n",
    sqrt(energia1 / pares), sqrt(energia2 / pares),
    estado.relacion, estado.piso,
    estado.bloques_calibracion > 0 ? "CALIBRANDO" : (estado.voz ? "VOZ" : "SILENCIO"),
    pico1, pico2
  );
}
