#include <ESP_I2S.h>
#include <math.h>

const int PIN_SCK = 26;   // D26 -> SCK
const int PIN_WS  = 25;   // D25 -> WS
const int PIN_SD  = 33;   // D33 -> SD
const uint32_t FRECUENCIA = 16000;
const int MUESTRAS = 512;

I2SClass i2s;
int32_t buffer[MUESTRAS * 2];       // izq, der, izq, der...

void setup() {
  Serial.begin(115200);
  delay(1000);
  i2s.setPins(PIN_SCK, PIN_WS, -1, PIN_SD);
  if (!i2s.begin(I2S_MODE_STD, FRECUENCIA, I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO)) {
    Serial.println("ERROR: no se pudo iniciar I2S.");
    while (true) delay(1000);
  }
}

void loop() {
  size_t bytesLeidos = i2s.readBytes((char *)buffer, sizeof(buffer));
  int pares = bytesLeidos / 8;
  if (pares == 0) return;

  double suma1 = 0, suma2 = 0;
  for (int i = 0; i < pares; i++) {
    suma1 += buffer[2 * i] >> 8;       // Mic 1 (izquierdo)
    suma2 += buffer[2 * i + 1] >> 8;   // Mic 2 (derecho)
  }
  double media1 = suma1 / pares, media2 = suma2 / pares;

  double energia1 = 0, energia2 = 0;
  for (int i = 0; i < pares; i++) {
    double v1 = (buffer[2 * i] >> 8) - media1;
    double v2 = (buffer[2 * i + 1] >> 8) - media2;
    energia1 += v1 * v1;
    energia2 += v2 * v2;
  }
  Serial.printf("Mic1_voz:%.0f,Mic2_ruido:%.0f\n", sqrt(energia1 / pares), sqrt(energia2 / pares));
}
