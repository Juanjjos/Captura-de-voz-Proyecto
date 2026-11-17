#include <ESP_I2S.h>
#include "filtro_ruido.h"

const int PIN_SCK = 26, PIN_WS = 25, PIN_SD = 33, PIN_LED = 2;
const bool USAR_DOS_MICROFONOS = true;   // false si solo tienes el mic 1
const int BLOQUE = 256;

I2SClass i2s;
int32_t crudo[BLOQUE * 2];
float m1[BLOQUE], m2[BLOQUE], filtrada[BLOQUE], original[BLOQUE];
int16_t paquete[BLOQUE * 2];
fr_estado_t estado;

void setup() {
  Serial.begin(921600);
  pinMode(PIN_LED, OUTPUT);
  i2s.setPins(PIN_SCK, PIN_WS, -1, PIN_SD);
  if (!i2s.begin(I2S_MODE_STD, 16000, I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO)) {
    while (true) { digitalWrite(PIN_LED, !digitalRead(PIN_LED)); delay(100); }
  }
  fr_iniciar(&estado, USAR_DOS_MICROFONOS);
}

void loop() {
  size_t bytes = i2s.readBytes((char *)crudo, sizeof(crudo));
  int n = bytes / 8;
  if (n == 0) return;
  for (int i = 0; i < n; i++) {
    m1[i] = (crudo[2 * i]     >> 8) / 8388608.0f;
    m2[i] = (crudo[2 * i + 1] >> 8) / 8388608.0f;
  }

  fr_procesar(&estado, m1, USAR_DOS_MICROFONOS ? m2 : NULL, filtrada, original, n);
  digitalWrite(PIN_LED, estado.voz ? HIGH : LOW);

  for (int i = 0; i < n; i++) {
    paquete[2 * i]     = (int16_t)(original[i] * 32767.0f);
    paquete[2 * i + 1] = (int16_t)(filtrada[i] * 32767.0f);
  }
  uint8_t cabecera[4] = {0xAA, 0x55, (uint8_t)(n & 0xFF), (uint8_t)(n >> 8)};
  Serial.write(cabecera, 4);
  Serial.write((uint8_t *)paquete, n * 4);
}
