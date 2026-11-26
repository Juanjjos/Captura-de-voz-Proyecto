/*
  EXPERIMENTO - Firmware de medicion (Arduino CLI)
  Sistema de Captura de Voz Inalambrica con Mitigacion de Ruido (ESP32)

  Envia al PC por USB, en cada instante, el MISMO sonido en dos versiones:
    - Canal izquierdo: microfono 1 SIN filtro (filtro desactivado)
    - Canal derecho:   microfono 1 CON filtro (filtro activado)
  Asi la comparacion usa exactamente la misma frase, posicion y ruido.

  Comandos que recibe del PC (los envia experimento.py):
    'r' -> reinicia el filtro (cada toma empieza desde el mismo estado)

  LED azul (GPIO 2): encendido = el sistema detecta voz.
  filtro_ruido.h debe estar en la misma carpeta que este archivo.
*/

#include <ESP_I2S.h>
#include "filtro_ruido.h"

const int PIN_SCK = 26;                 // D26 -> SCK
const int PIN_WS  = 25;                 // D25 -> WS
const int PIN_SD  = 33;                 // D33 -> SD
const int PIN_LED = 2;
const bool USAR_DOS_MICROFONOS = true;  // false si solo tienes el microfono 1
const int BLOQUE = 256;                 // 16 ms a 16 kHz

I2SClass i2s;
int32_t crudo[BLOQUE * 2];
float m1[BLOQUE], m2[BLOQUE], filtrada[BLOQUE], original[BLOQUE];
int16_t paquete[BLOQUE * 2];
fr_estado_t estado;
uint32_t secuencia = 0;

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
  // Comandos del PC
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == 'r') fr_iniciar(&estado, USAR_DOS_MICROFONOS);
  }

  // 1. Leer los dos microfonos
  size_t bytes = i2s.readBytes((char *)crudo, sizeof(crudo));
  int n = bytes / 8;
  if (n == 0) return;
  for (int i = 0; i < n; i++) {
    m1[i] = (crudo[2 * i]     >> 8) / 8388608.0f;
    m2[i] = (crudo[2 * i + 1] >> 8) / 8388608.0f;
  }

  // 2. Misma entrada, dos salidas: sin filtro y con filtro
  fr_procesar(&estado, m1, USAR_DOS_MICROFONOS ? m2 : NULL, filtrada, original, n);
  digitalWrite(PIN_LED, estado.voz ? HIGH : LOW);

  // 3. Enviar cabecera versionada con contador para detectar bloques perdidos.
  for (int i = 0; i < n; i++) {
    paquete[2 * i]     = (int16_t)(original[i] * 32767.0f);
    paquete[2 * i + 1] = (int16_t)(filtrada[i] * 32767.0f);
  }
  uint8_t cabecera[8] = {
    0xAA, 0x55,
    (uint8_t)(n & 0xFF), (uint8_t)(n >> 8),
    (uint8_t)(secuencia & 0xFF), (uint8_t)((secuencia >> 8) & 0xFF),
    (uint8_t)((secuencia >> 16) & 0xFF), (uint8_t)((secuencia >> 24) & 0xFF)
  };
  Serial.write(cabecera, sizeof(cabecera));
  Serial.write((uint8_t *)paquete, n * 4);
  secuencia++;
}
