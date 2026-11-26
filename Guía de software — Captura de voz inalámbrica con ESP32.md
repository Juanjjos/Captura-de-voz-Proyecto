# Guía de software — Captura de voz inalámbrica con ESP32



| Etapa | Qué se hace | Códigos | Entorno |
| --- | --- | --- | --- |
| 0 | Instalar el software | — | PC |
| 1 | Verificar los micrófonos | `prueba_microfonos` | VS Code + Arduino CLI |
| 2 | Probar el filtro por USB | `grabador_serial` | VS Code + Arduino CLI |
| 3 | Grabar y medir en el PC | 4 y 5 | Python |
| 4 | Cargar el firmware Bluetooth | 2, 6 y 7 | VS Code + ESP-IDF |
| 5 | Conectar al PC y grabar por Bluetooth | — | Windows + Audacity |
| 6 | Pruebas finales | 5 | Python |

> **Fuentes ejecutables:** usa los archivos del repositorio indicados en cada
> etapa. Los bloques “Código 1–7” de esta guía son versiones de referencia
> anteriores y no incluyen todas las correcciones actuales; no los copies
> encima de los archivos fuente.

## Etapa 0: Instalar el software

Todo es gratuito. Los pasos son para Windows.

**0.1 Driver USB del ESP32**

1. Conecta el ESP32 por USB y abre el Administrador de dispositivos (clic derecho en Inicio).
2. En Puertos (COM y LPT) debe aparecer "CP210x" o "CH340" con un número COM. Anótalo.
3. Si no aparece o tiene un signo de advertencia, instala el driver del chip de tu placa: CP210x (Silicon Labs) o CH340 (WCH). Reinicia el PC y revisa de nuevo.

**0.2 Arduino CLI y el paquete ESP32**

Arduino IDE no es necesario. Instala Arduino CLI desde la documentación oficial de Arduino y asegúrate de que `arduino-cli` se pueda ejecutar en la terminal integrada de VS Code. Luego ejecuta:

```
arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32
arduino-cli core list
arduino-cli board list
```

Confirma que `esp32:esp32` esté instalado y que la versión sea 3.x. La placa de esta práctica es `esp32:esp32:esp32` (ESP32 Dev Module). Si la descarga se interrumpe, vuelve a ejecutar `arduino-cli core install esp32:esp32` hasta que finalice.

**0.3 Python y sus librerías**

1. Descarga Python 3 desde python.org e instálalo. En la primera pantalla marca **"Add python.exe to PATH"**.
2. Abre la terminal (tecla Windows, escribe `cmd`, Enter) y ejecuta:

Desde la raíz del repositorio ejecuta:

```
python -m pip install -r requirements.txt
```

3. Comprueba con `python --version`: debe mostrar Python 3.

**0.4 Audacity**

Descárgalo desde audacityteam.org e instálalo.

**0.5 VS Code y ESP-IDF (necesario desde la Etapa 4)**

1. Instala VS Code desde code.visualstudio.com.
2. En VS Code abre Extensiones (Ctrl+Shift+X), busca **ESP-IDF** (de Espressif) e instálala.
3. Abre la paleta de comandos (Ctrl+Shift+P) y ejecuta **ESP-IDF: Configure ESP-IDF Extension**.
4. Elige **Express**, la versión estable más reciente de **ESP-IDF v5.x** y una carpeta sin espacios en la ruta (por ejemplo `C:\esp`). La instalación tarda de 15 a 40 minutos.

**0.6 Carpeta del proyecto**

Los códigos ya están dentro de esta carpeta del repositorio. Puedes trabajar directamente aquí o copiar el repositorio completo a una ruta corta, por ejemplo `C:\proyecto_voz`; guarda las grabaciones junto a `grabar_audio.py`.

**Verificación de la Etapa 0**

- [ ] El ESP32 aparece como puerto COM y anotaste el número.
- [ ] Arduino CLI muestra el core esp32 3.x y `arduino-cli board list` detecta la placa.
- [ ] `python --version` responde y `pip install` terminó sin errores.
- [ ] Audacity abre.
- [ ] ESP-IDF quedó instalado en VS Code (puede esperar hasta la Etapa 4).

## Etapa 1: Verificar los micrófonos (código 1)

Esta etapa confirma que el cableado funciona: cada micrófono debe responder en su propia línea del Serial Plotter.

**1.1 Crear el programa**

1. Abre VS Code en la raíz del repositorio y ejecuta los comandos de Arduino CLI indicados abajo.
2. No es necesario volver a copiar el código 1: el sketch ya está guardado en el archivo.

**Código 1 (referencia antigua): fuente actual `arduino\prueba_microfonos\prueba_microfonos.ino`**

```cpp
#include <ESP_I2S.h>

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
```

**1.2 Subirlo al ESP32**

1. Conecta el ESP32 por USB y consulta el puerto con `arduino-cli board list`.
2. Desde la raíz del repositorio compila y sube (reemplaza `COM3` por tu puerto):

   ```
   arduino-cli compile --fqbn esp32:esp32:esp32 .\arduino\prueba_microfonos
   arduino-cli upload -p COM3 --fqbn esp32:esp32:esp32 .\arduino\prueba_microfonos
   ```

3. Si se queda en `Connecting.....`, mantén presionado **BOOT** hasta que avance.

**1.3 Probar**

1. En VS Code ejecuta `arduino-cli monitor -p COM3 -c baudrate=115200` (cambia el COM).
2. Las líneas muestran niveles RMS/picos normalizados; `Estado:0` es calibración,
   `Estado:1` silencio y `Estado:2` voz. La escala completa es 1.0.
3. Haz estas pruebas:

| Prueba | Resultado correcto |
| --- | --- |
| Silencio | Dos valores RMS bajos y estables; termina la calibración |
| Hablar cerca del micrófono 1 | Sube `Mic1_voz`; detector cambia a `Estado:2` |
| Hablar cerca del micrófono 2 | Sube `Mic2_ruido`; no debe confundirse con voz principal |
| Aplaudir lejos de ambos | Suben las dos parecido |

Sal del monitor con `Ctrl+C` antes de compilar/subir otro sketch. La prueba
emite datos numéricos para poder verlos también en un Serial Plotter.

**Verificación de la Etapa 1**

- [ ] El código se subió sin errores.
- [ ] Cada micrófono hace subir su propia línea.
- [ ] Cierra el Serial Plotter antes de seguir: si queda abierto, ocupa el puerto COM.

## Etapa 2: Probar el filtro por USB (códigos 2 y 3)

El ESP32 filtra el ruido y envía al PC, por el cable USB, dos canales a la vez: el izquierdo es el audio original y el derecho el filtrado. Así se comparan con exactamente el mismo sonido.

La implementación actual está en `arduino\grabador_serial\filtro_ruido.h` y
es compartida con Bluetooth. La compuerta reduce más el nivel cuando no detecta
voz y exige que el sonido cumpla el detector durante 64 ms; esto ayuda con
golpes breves, pero no puede separar perfectamente dos sonidos simultáneos que
llegan casi igual a ambos micrófonos. Para comparar, graba primero silencio,
luego golpes sobre la mesa y finalmente voz cerca del micrófono 1.

**2.1 Crear el programa con sus dos archivos**

1. El sketch está en `arduino\grabador_serial\grabador_serial.ino`.
2. El archivo `filtro_ruido.h` ya está en la misma carpeta del sketch; no es necesario volver a crear la pestaña ni copiar el código.

**Código 2 (referencia antigua): fuente actual `arduino\grabador_serial\filtro_ruido.h`**

```c
#pragma once
#include <math.h>
#include <stdbool.h>
#include <string.h>

// ---------------- Ajustes ----------------
#define FR_FS            16000.0f // frecuencia de muestreo (Hz)
#define FR_CORTE_BAJO      300.0f // Hz: elimina zumbidos graves
#define FR_CORTE_ALTO     3400.0f // Hz: elimina siseos agudos
#define FR_TAPS              64   // longitud del filtro adaptativo (4 ms)
#define FR_RETARDO           16   // retardo del mic 1 (1 ms)
#define FR_MU              0.05f  // velocidad de aprendizaje
#define FR_RELACION_VOZ     2.0f  // energia mic1/mic2 para considerar que hay voz
#define FR_GANANCIA_GATE   0.25f  // volumen en silencios (0.25 = -12 dB)
#define FR_GANANCIA         8.0f  // amplificacion final
#define FR_MAX_BLOQUE       512
#define FR_PI       3.14159265f

typedef struct { float b0, b1, b2, a1, a2, z1, z2; } fr_biquad_t;

typedef struct {
  bool dos_mics;
  fr_biquad_t hp1, lp1, hp2, lp2;
  float dc_x, dc_y;
  float w[FR_TAPS];
  float xb[2 * FR_TAPS];
  int pos;
  float pot_ref;
  float retardo[FR_RETARDO];
  int pos_ret;
  float piso;
  bool primer_bloque;
  float g;
  bool voz;
  float t1[FR_MAX_BLOQUE], t2[FR_MAX_BLOQUE];
} fr_estado_t;

static inline float fr_limitar(float x) { return x > 1.0f ? 1.0f : (x < -1.0f ? -1.0f : x); }

// tipo 0 = pasa-altos, 1 = pasa-bajos (Butterworth de 2.o orden)
static inline void fr_biquad_iniciar(fr_biquad_t *f, int tipo, float fc, float fs) {
  float w0 = 2.0f * FR_PI * fc / fs, c = cosf(w0), alfa = sinf(w0) / (2.0f * 0.7071f);
  float a0 = 1.0f + alfa;
  if (tipo == 0) { f->b0 = (1.0f + c) / 2.0f; f->b1 = -(1.0f + c); f->b2 = (1.0f + c) / 2.0f; }
  else           { f->b0 = (1.0f - c) / 2.0f; f->b1 = 1.0f - c;    f->b2 = (1.0f - c) / 2.0f; }
  f->a1 = -2.0f * c; f->a2 = 1.0f - alfa;
  f->b0 /= a0; f->b1 /= a0; f->b2 /= a0; f->a1 /= a0; f->a2 /= a0;
  f->z1 = f->z2 = 0.0f;
}

static inline float fr_biquad(fr_biquad_t *f, float x) {
  float y = f->b0 * x + f->z1;
  f->z1 = f->b1 * x - f->a1 * y + f->z2;
  f->z2 = f->b2 * x - f->a2 * y;
  return y;
}

static inline void fr_iniciar(fr_estado_t *s, bool dos_mics) {
  memset(s, 0, sizeof(*s));
  s->dos_mics = dos_mics;
  fr_biquad_iniciar(&s->hp1, 0, FR_CORTE_BAJO, FR_FS);
  fr_biquad_iniciar(&s->lp1, 1, FR_CORTE_ALTO, FR_FS);
  fr_biquad_iniciar(&s->hp2, 0, FR_CORTE_BAJO, FR_FS);
  fr_biquad_iniciar(&s->lp2, 1, FR_CORTE_ALTO, FR_FS);
  s->primer_bloque = true;
  s->g = 1.0f;
}

// m1: mic 1 (voz), m2: mic 2 (ruido, NULL si hay 1 solo mic)
// filtrada: salida con reduccion de ruido, original: mic 1 sin filtrar
static inline void fr_procesar(fr_estado_t *s, const float *m1, const float *m2,
                               float *filtrada, float *original, int n) {
  if (n > FR_MAX_BLOQUE) n = FR_MAX_BLOQUE;
  bool dos = s->dos_mics && m2 != NULL;

  // 1. Pasa-banda de voz y energia de cada microfono
  float e1 = 0.0f, e2 = 0.0f;
  for (int i = 0; i < n; i++) {
    float y = m1[i] - s->dc_x + 0.995f * s->dc_y;
    s->dc_x = m1[i]; s->dc_y = y;
    if (original) original[i] = fr_limitar(y * FR_GANANCIA);

    float a = fr_biquad(&s->lp1, fr_biquad(&s->hp1, m1[i]));
    s->t1[i] = a; e1 += a * a;
    if (dos) {
      float b = fr_biquad(&s->lp2, fr_biquad(&s->hp2, m2[i]));
      s->t2[i] = b; e2 += b * b;
    }
  }
  float rms1 = sqrtf(e1 / n);

  // 2. Detector de voz
  if (s->primer_bloque) { s->piso = rms1; s->primer_bloque = false; }
  bool voz = dos ? (rms1 > 2.0f * s->piso && e1 > FR_RELACION_VOZ * e2)
                 : (rms1 > 3.0f * s->piso);
  if (!voz) s->piso = 0.9f * s->piso + 0.1f * rms1;
  else      s->piso *= 1.005f;
  s->voz = voz;
  float objetivo = voz ? 1.0f : FR_GANANCIA_GATE;

  for (int i = 0; i < n; i++) {
    float salida = s->t1[i];

    // 3. Cancelacion adaptativa (NLMS): estima el ruido con el mic 2 y lo resta
    if (dos) {
      float d = s->retardo[s->pos_ret];
      s->retardo[s->pos_ret] = s->t1[i];
      s->pos_ret = (s->pos_ret + 1) % FR_RETARDO;

      float x = s->t2[i];
      s->pos = (s->pos == 0) ? FR_TAPS - 1 : s->pos - 1;
      s->xb[s->pos] = x;
      s->xb[s->pos + FR_TAPS] = x;
      const float *v = &s->xb[s->pos];
      s->pot_ref = 0.995f * s->pot_ref + 0.005f * x * x;

      float estimado = 0.0f;
      for (int k = 0; k < FR_TAPS; k++) estimado += s->w[k] * v[k];
      float err = d - estimado;

      if (!voz) {   // solo aprende cuando no hablas
        float paso = FR_MU * err / (FR_TAPS * s->pot_ref + 1e-10f);
        for (int k = 0; k < FR_TAPS; k++) s->w[k] += paso * v[k];
      }
      salida = err;
    }

    // 4. Compuerta de ruido con transicion suave
    s->g += 0.002f * (objetivo - s->g);
    if (filtrada) filtrada[i] = fr_limitar(salida * s->g * FR_GANANCIA);
  }
}
```

**Código 3 (referencia antigua): fuente actual `arduino\grabador_serial\grabador_serial.ino`**

```cpp
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
```

**2.2 Subirlo y comprobar**

1. Clic en **Subir**. Usa el botón BOOT si se queda en `Connecting.....`.
2. No abras el Monitor Serie ni el Serial Plotter: este programa envía audio en binario, no texto.
3. Habla cerca del micrófono 1: el **LED azul** de la placa debe encenderse mientras hablas y apagarse en los silencios.
4. Si el LED parpadea rápido sin parar, el I2S no inició: revisa la versión 3.x del paquete ESP32.

**Verificación de la Etapa 2**

- [ ] Compiló y se subió sin errores.
- [ ] El LED azul se enciende al hablar y se apaga en silencio.
- [ ] Si el LED se queda encendido con solo ruido, sube `FR_RELACION_VOZ` a 3.0 en el código 2. Si casi nunca enciende al hablar, bájalo a 1.5.

## Etapa 3: Grabar y medir en el PC (códigos 4 y 5)

El código 4 graba lo que envía el ESP32 y el código 5 calcula cuánto ruido quitó el filtro.

**3.1 Guardar los scripts**

Los archivos `grabar_audio.py` y `analizar_snr.py` ya están en la carpeta principal del proyecto. Abre una terminal en esa carpeta para ejecutar los comandos de las secciones siguientes.

**Código 4 (referencia antigua): fuente actual `grabar_audio.py`**

```python
import struct
import sys
import wave

import numpy as np

FS = 16000
BAUDIOS = 921600


def extraer_bloques(buf):
    bloques = []
    while True:
        i = buf.find(b"\xaa\x55")
        if i < 0:
            return bloques, buf[-1:]
        if len(buf) < i + 4:
            return bloques, buf[i:]
        n = struct.unpack_from("<H", buf, i + 2)[0]
        if n == 0 or n > 512:
            buf = buf[i + 2:]
            continue
        fin = i + 4 + n * 4
        if len(buf) < fin:
            return bloques, buf[i:]
        bloques.append(np.frombuffer(bytes(buf[i + 4:fin]), dtype="<i2").reshape(-1, 2))
        buf = buf[fin:]


def guardar_wav(nombre, audio):
    with wave.open(nombre, "wb") as w:
        w.setnchannels(audio.shape[1] if audio.ndim == 2 else 1)
        w.setsampwidth(2)
        w.setframerate(FS)
        w.writeframes(audio.astype("<i2").tobytes())


def main():
    import serial

    puerto = sys.argv[1] if len(sys.argv) > 1 else "COM3"
    segundos = float(sys.argv[2]) if len(sys.argv) > 2 else 10
    archivo = sys.argv[3] if len(sys.argv) > 3 else "grabacion.wav"

    with serial.Serial(puerto, BAUDIOS, timeout=1) as ser:
        ser.reset_input_buffer()
        print(f"Grabando {segundos:.0f} s desde {puerto}...")
        print("Sugerencia: deja 3 s de solo ruido al inicio y luego habla.")
        objetivo = int(segundos * FS)
        bloques, buf, total, ultimo = [], bytearray(), 0, -1
        while total < objetivo:
            datos = ser.read(4096)
            if not datos:
                print("No llegan datos. Revisa el puerto y que la Prueba 2 este cargada.")
                return
            nuevos, buf = extraer_bloques(buf + datos)
            buf = bytearray(buf)
            bloques += nuevos
            total += sum(len(b) for b in nuevos)
            seg = total // FS
            if seg != ultimo:
                print(f"  {seg} s", end="\r")
                ultimo = seg

    audio = np.concatenate(bloques)[:objetivo]
    guardar_wav(archivo, audio)
    base = archivo.rsplit(".", 1)[0]
    guardar_wav(base + "_original.wav", audio[:, 0])
    guardar_wav(base + "_filtrada.wav", audio[:, 1])
    print(f"\nListo: {archivo}, {base}_original.wav y {base}_filtrada.wav")


if __name__ == "__main__":
    main()
```

**Código 5 (referencia antigua): fuente actual `analizar_snr.py`**

```python
import sys

import matplotlib.pyplot as plt
import numpy as np
from scipy.io import wavfile


def leer(nombre, canal=0):
    fs, x = wavfile.read(nombre)
    if x.ndim == 2:
        x = x[:, canal]
    return fs, x.astype(np.float64)


def snr(x, fs, ms=20):
    n = int(fs * ms / 1000)
    t = len(x) // n
    e = np.sort(np.mean(x[: t * n].reshape(t, n) ** 2, axis=1)) + 1e-9
    k = max(1, t // 10)
    p_voz, p_ruido = e[-k:].mean(), e[:k].mean()
    return 10 * np.log10(max(p_voz - p_ruido, 1e-9) / p_ruido), p_ruido


def main():
    if len(sys.argv) == 3:
        fs, sin = leer(sys.argv[1])
        _, con = leer(sys.argv[2])
        base = sys.argv[2].rsplit(".", 1)[0]
    elif len(sys.argv) == 2:
        fs, sin = leer(sys.argv[1], 0)
        _, con = leer(sys.argv[1], 1)
        base = sys.argv[1].rsplit(".", 1)[0]
    else:
        print("Uso: python analizar_snr.py grabacion.wav  |  sin_filtro.wav con_filtro.wav")
        return

    snr_sin, ruido_sin = snr(sin, fs)
    snr_con, ruido_con = snr(con, fs)
    print(f"SNR sin filtro : {snr_sin:6.1f} dB")
    print(f"SNR con filtro : {snr_con:6.1f} dB")
    print(f"Mejora         : {snr_con - snr_sin:6.1f} dB")
    print(f"Reduccion del ruido de fondo: {10 * np.log10(ruido_sin / ruido_con):.1f} dB")

    fig, ejes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for eje, x, titulo in [(ejes[0], sin, f"Sin filtro (SNR {snr_sin:.1f} dB)"),
                           (ejes[1], con, f"Con filtro (SNR {snr_con:.1f} dB)")]:
        eje.specgram(x, NFFT=512, Fs=fs, noverlap=384, cmap="magma")
        eje.set_title(titulo)
        eje.set_ylabel("Frecuencia (Hz)")
    ejes[1].set_xlabel("Tiempo (s)")
    plt.tight_layout()
    salida = base + "_espectrogramas.png"
    plt.savefig(salida, dpi=150)
    print("Grafica guardada en", salida)
    plt.show()


if __name__ == "__main__":
    main()
```

**3.2 Grabar una prueba**

1. Ten el código 3 cargado en el ESP32 y el Monitor Serie de Arduino cerrado.
2. Abre PowerShell en la carpeta principal del repositorio (la que contiene `grabar_audio.py`). Si copiaste el repositorio a `C:\proyecto_voz`, entra con `Set-Location C:\proyecto_voz`.
3. Pon una fuente de ruido a volumen fijo, por ejemplo un celular con ruido blanco a 1 m.
4. Ejecuta, cambiando COM3 por tu puerto:

```
python grabar_audio.py COM3 15 prueba1.wav
```

5. Durante los primeros **3 segundos no hables** (solo ruido). Luego lee una frase fija durante unos 10 segundos.
6. Al terminar se crean `prueba1.wav` (estéreo), `prueba1_original.wav`, `prueba1_filtrada.wav` y `prueba1_continuidad_usb.json`. El JSON informa la continuidad USB usando el número de secuencia de cada bloque. Escucha los WAV en Audacity.

**3.3 Medir**

```
python analizar_snr.py prueba1.wav
```

Muestra una estimación de SNR y guarda `prueba1_espectrogramas.png`; úsala solo como referencia porque los segmentos casi silenciosos pueden inflar el resultado. Para medir saturación del WAV ejecuta:

```
python evaluar_prueba.py prueba1.wav
```

El analizador guarda un JSON con duración y porcentaje de muestras cercanas al máximo digital. Si la saturación no es baja, reduce la ganancia antes de comparar calidad.

**Verificación de la Etapa 3**

- [ ] La grabación dura lo pedido y se oye tu voz.
- [ ] La versión filtrada tiene menos ruido de fondo al escucharla.
- [ ] Se guardaron duración, saturación y continuidad USB junto con la captura. Usa SNR solo como métrica secundaria.
- [ ] Si la voz filtrada suena cortada al inicio de las palabras, baja `FR_RELACION_VOZ`. Si suena saturada, baja `FR_GANANCIA` a 4.0. Después de cambiar el código 2, vuelve a subir el código 3.

## Etapa 4: Firmware Bluetooth en ESP-IDF (códigos 2, 6 y 7)

Este firmware hace que el ESP32 aparezca en el PC como unos audífonos manos libres llamados **MicESP32** y envíe tu voz filtrada. El botón BOOT activa o desactiva el filtro, y el LED azul queda encendido mientras el filtro está activo.

**4.1 Crear la estructura del proyecto**

La estructura ya está creada en la carpeta `microfono_bt` de este proyecto. Debe verse así:

```
microfono_bt\
├── CMakeLists.txt          (código 7a)
├── sdkconfig.defaults      (código 7c)
└── main\
    ├── CMakeLists.txt      (código 7b)
    ├── main.c              (código 6)
    └── filtro_ruido.h      (código 2, el mismo de la Etapa 2)
```

Abre `microfono_bt` como carpeta del proyecto en VS Code; no hace falta volver a crear ni copiar estos archivos. Hay dos archivos llamados `CMakeLists.txt` con contenido distinto: uno en la carpeta principal y otro dentro de `main`.

**Código 7a (referencia): fuente `microfono_bt\CMakeLists.txt`**

```cmake
cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(microfono_bt)
```

**Código 7b (referencia antigua): fuente actual `microfono_bt\main\CMakeLists.txt`**

```cmake
idf_component_register(SRCS "main.c"
                       INCLUDE_DIRS ".")
```

**Código 7c (referencia): fuente `microfono_bt\sdkconfig.defaults`**

```
CONFIG_BT_ENABLED=y
CONFIG_BT_BLUEDROID_ENABLED=y
CONFIG_BT_CLASSIC_ENABLED=y
CONFIG_BT_BLE_ENABLED=n
CONFIG_BT_SSP_ENABLED=y
CONFIG_BT_HFP_ENABLE=y
CONFIG_BT_HFP_CLIENT_ENABLE=y
CONFIG_BT_HFP_AUDIO_DATA_PATH_HCI=y
CONFIG_BT_HFP_WBS_ENABLE=y
CONFIG_BTDM_CTRL_MODE_BR_EDR_ONLY=y
CONFIG_BTDM_CTRL_BR_EDR_SCO_DATA_PATH_HCI=y
CONFIG_BTDM_CTRL_BR_EDR_MAX_SYNC_CONN=1
CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_240=y
```

**Código 6 (referencia antigua): fuente actual `microfono_bt\main\main.c`**

```c
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/stream_buffer.h"
#include "esp_log.h"
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

static void datos_entrantes(const uint8_t *buf, uint32_t len) {
  (void)buf; (void)len;   // audio del PC hacia el ESP32: no se usa
}

static uint32_t datos_salientes(uint8_t *buf, uint32_t len) {
  size_t n = xStreamBufferReceive(cola_audio, buf, len, 0);
  if (n < len) memset(buf + n, 0, len - n);
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
        esp_hf_client_register_data_callback(datos_entrantes, datos_salientes);
        xStreamBufferReset(cola_audio);
        audio_conectado = true;
        ESP_LOGI(TAG, "Audio abierto a %d Hz", frecuencia_bt);
      } else if (p->audio_stat.state == ESP_HF_CLIENT_AUDIO_STATE_DISCONNECTED) {
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
  fr_iniciar(&estado, USAR_DOS_MICROFONOS);
  int boton_antes = 1;

  while (1) {
    size_t bytes = 0;
    i2s_channel_read(rx, crudo, sizeof(crudo), &bytes, portMAX_DELAY);
    int n = bytes / 8;
    if (n == 0) continue;
    for (int i = 0; i < n; i++) {
      m1[i] = (crudo[2 * i]     >> 8) / 8388608.0f;
      m2[i] = (crudo[2 * i + 1] >> 8) / 8388608.0f;
    }

    fr_procesar(&estado, m1, USAR_DOS_MICROFONOS ? m2 : NULL, filtrada, original, n);

    int boton = gpio_get_level(PIN_BOTON);
    if (boton == 0 && boton_antes == 1) {
      filtro_activo = !filtro_activo;
      gpio_set_level(PIN_LED, filtro_activo);
      ESP_LOGI(TAG, "Filtro %s", filtro_activo ? "ACTIVADO" : "DESACTIVADO");
    }
    boton_antes = boton;

    if (audio_conectado) {
      const float *fuente = filtro_activo ? filtrada : original;
      int paso = (frecuencia_bt == 8000) ? 2 : 1, k = 0;
      for (int i = 0; i < n; i += paso) salida[k++] = (int16_t)(fuente[i] * 32767.0f);
      xStreamBufferSend(cola_audio, salida, k * sizeof(int16_t), 0);
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
  iniciar_i2s();

  ESP_ERROR_CHECK(esp_bt_controller_mem_release(ESP_BT_MODE_BLE));
  esp_bt_controller_config_t bt_cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
  ESP_ERROR_CHECK(esp_bt_controller_init(&bt_cfg));
  ESP_ERROR_CHECK(esp_bt_controller_enable(ESP_BT_MODE_CLASSIC_BT));
  ESP_ERROR_CHECK(esp_bluedroid_init());
  ESP_ERROR_CHECK(esp_bluedroid_enable());

  esp_bt_gap_register_callback(evento_gap);
  esp_bt_gap_set_device_name(NOMBRE_BT);

  esp_bt_cod_t cod = {0};
  cod.major = ESP_BT_COD_MAJOR_DEV_AV;
  cod.minor = 0x02;
  cod.service = ESP_BT_COD_SRVC_AUDIO;
  esp_bt_gap_set_cod(cod, ESP_BT_SET_COD_ALL);

  esp_bt_io_cap_t iocap = ESP_BT_IO_CAP_NONE;
  esp_bt_gap_set_security_param(ESP_BT_SP_IOCAP_MODE, &iocap, sizeof(uint8_t));
  esp_bt_pin_code_t pin = {0};
  esp_bt_gap_set_pin(ESP_BT_PIN_TYPE_VARIABLE, 0, pin);

  esp_hf_client_register_callback(evento_hf);
  ESP_ERROR_CHECK(esp_hf_client_init());

  esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
  ESP_LOGI(TAG, "Listo. Busca \"%s\" en el Bluetooth del PC", NOMBRE_BT);

  int num = esp_bt_gap_get_bond_device_num();
  if (num > 0) {
    esp_bd_addr_t lista[num];
    esp_bt_gap_get_bond_device_list(&num, lista);
    ESP_LOGI(TAG, "Reconectando al ultimo equipo emparejado...");
    esp_hf_client_connect(lista[0]);
  }

  xTaskCreatePinnedToCore(tarea_audio, "audio", 4096, NULL, 5, NULL, 1);
  xTaskCreate(tarea_envio, "envio", 3072, NULL, 5, NULL);
}
```

**4.2 Abrir y configurar el proyecto en VS Code**

1. VS Code → Archivo → Abrir carpeta → elige `microfono_bt`.
2. Ctrl+Shift+P → **ESP-IDF: Set Espressif Device Target** → **esp32**. Si pregunta por un adaptador de depuración, elige la primera opción: no afecta la carga por USB.
3. Ctrl+Shift+P → **ESP-IDF: Select Port to Use** → tu COM.
4. Ctrl+Shift+P → **ESP-IDF: SDK Configuration Editor (menuconfig)**. Busca y confirma que estén así:
   - Classic Bluetooth: activado, con **Hands Free/Handset Profile** y su rol **Hands Free Unit** activados.
   - Audio data path del HFP: **HCI**.
   - En Controller Options, BR/EDR Sync (SCO/eSCO) default data path: **HCI**.
   - Wide Band Speech (mSBC): activado.
5. Si cambiaste algo, guarda en el editor.

`sdkconfig.defaults` solo se aplica cuando el proyecto no tiene aún un archivo `sdkconfig`. Si ya compilaste antes de crear `sdkconfig.defaults`, borra el archivo `sdkconfig` y la carpeta `build` y compila de nuevo.

**4.3 Compilar, cargar y ver mensajes**

1. Ctrl+Shift+P → **ESP-IDF: Build, Flash and Start a Monitor on your Device** (o el icono de la llama en la barra inferior).
2. La primera compilación tarda varios minutos. Si se queda en `Connecting...`, mantén presionado BOOT.
3. En el monitor debe aparecer: `Listo. Busca "MicESP32" en el Bluetooth del PC`.
4. Pulsa BOOT: debe aparecer `Filtro DESACTIVADO` y apagarse el LED azul. Pulsa de nuevo para activarlo.
5. Para salir del monitor: Ctrl+\].

**Verificación de la Etapa 4**

- [ ] Compiló sin errores. Si hay alguno, copia el mensaje completo y pídeme la corrección.
- [ ] El monitor muestra "Listo. Busca MicESP32...".
- [ ] BOOT alterna el filtro y el LED azul.

## Etapa 5: Conectar al PC y grabar por Bluetooth

El PC reconoce el ESP32 como un micrófono de audífonos manos libres. El USB solo le da energía: el audio viaja por Bluetooth.

**5.1 Emparejar**

1. Con el ESP32 encendido, en Windows abre Configuración → **Bluetooth y dispositivos** → **Agregar dispositivo** → **Bluetooth**.
2. Elige **MicESP32**. Si pide un PIN, escribe `1234`.
3. En el monitor de VS Code deben aparecer "Emparejado con..." y "Conectado al PC como manos libres".

**5.2 Seleccionar el micrófono**

1. Configuración → Sistema → **Sonido** → Entrada.
2. Elige el micrófono de **MicESP32** (puede llamarse "Auriculares manos libres" o "Hands-Free").

**5.3 Grabar en Audacity**

1. Abre Audacity. En la barra de dispositivos elige como micrófono el de **MicESP32** y canales de grabación: **1 (Mono)**.
2. Abajo a la izquierda, en "Frecuencia del proyecto", pon **16000 Hz**.
3. Pulsa **Grabar** (botón rojo). Al empezar, Windows abre el canal de audio y el monitor muestra "Audio abierto a 16000 Hz" (o 8000 Hz si el PC no soporta banda ancha).
4. Habla: debes ver la forma de onda de tu voz.

**5.4 Escuchar en vivo (opcional)**

Panel de control de sonido (Win+R → `mmsys.cpl`) → Grabar → micrófono de MicESP32 → Propiedades → Escuchar → marca **Escuchar este dispositivo**. Usa audífonos para evitar acople.

**5.5 Grabar la comparación por Bluetooth**

1. Pon la misma fuente de ruido de la Etapa 3, al mismo volumen.
2. Con el filtro **desactivado** (LED apagado): graba 3 s de solo ruido y luego la frase fija. Exporta con Archivo → Exportar audio → WAV 16 bits, como `bt_sin_filtro.wav`.
3. Pulsa BOOT (LED encendido) y repite exactamente igual. Exporta como `bt_con_filtro.wav`.
4. Mide en la terminal:

```
python analizar_snr.py bt_sin_filtro.wav bt_con_filtro.wav
```

Para registrar niveles de saturación, continuidad de la sesión y alcance, guarda
el log ESP-IDF durante la prueba y ejecuta `evaluar_prueba.py` con el WAV
Bluetooth. El reporte de SNR anterior es aproximado y no debe usarse como único
resultado.

**Verificación de la Etapa 5**

- [ ] MicESP32 aparece emparejado y como micrófono en Windows.
- [ ] Audacity graba tu voz por Bluetooth.
- [ ] Se guarda el WAV y el log con estado de conexión, saturación y underflows.
- [ ] La comparación con/sin filtro se realiza con el mismo procedimiento y se reportan métricas repetibles.

## Etapa 6: Pruebas finales

Estas pruebas demuestran que el proyecto cumple su objetivo. Mantén siempre la misma frase, la misma distancia boca-micrófono 1 y la misma posición de los micrófonos.

**6.1 Reducción de ruido en distintas condiciones**

1. Mide el nivel de ruido con una app de sonómetro en el celular, junto al micrófono 1.
2. Para cada fila de la tabla: graba sin y con filtro (Etapa 3 por USB o Etapa 5 por Bluetooth) y mide con el código 5.
3. Anota los resultados aquí mismo y conserva los informes JSON de cada captura; no uses la SNR como única evidencia.

| Prueba | Tipo de ruido | Nivel de ruido (dB) | Distancia boca-mic 1 (cm) | Vía | SNR sin filtro (dB) | SNR con filtro (dB) | Mejora (dB) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Ruido blanco | \~50 | 20 | Bluetooth |  |  |  |
| 2 | Ruido blanco | \~60 | 20 | Bluetooth |  |  |  |
| 3 | Ruido blanco | \~70 | 20 | Bluetooth |  |  |  |
| 4 | Voces de fondo o música | \~60 | 20 | Bluetooth |  |  |  |
| 5 | Ruido blanco | \~60 | 50 | Bluetooth |  |  |  |

**6.2 Inteligibilidad**

1. Lee una lista de 20 palabras con ruido de \~60 dB, una vez sin filtro y otra con filtro.
2. Otra persona escucha cada grabación y escribe lo que entiende.
3. Calcula el porcentaje de palabras correctas en cada caso.

**6.3 Alcance**

1. Repite una grabación de 30 s a distancias medidas (por ejemplo 1, 2 y 3 m), con línea de vista y el mismo volumen. Haz tres repeticiones por distancia.
2. Para cada repetición guarda el WAV de Audacity y el log del monitor ESP-IDF en archivos separados. Reinicia el ESP32 antes de cada repetición para que los contadores acumulados se puedan comparar.
3. Guarda los WAV y logs dentro de `microfono_bt` y, desde la raíz del
   repositorio, ejecuta el análisis con la distancia real en metros:

   ```
   python .\evaluar_prueba.py .\microfono_bt\bt_1m.wav --distance-m 1 --firmware-log .\microfono_bt\bt_1m.log
   ```

4. Reporta la mayor distancia en la que las tres pruebas terminaron sin desconexión ni cortes audibles. El firmware informa pérdidas locales de cola y bytes HFP rellenados con silencio; no mide directamente paquetes perdidos por radio.

**6.4 Latencia**

Graba simultáneamente el mismo sonido de prueba en una pista de referencia y en la entrada Bluetooth. Alinea ambas capturas al mismo inicio y expórtalas como WAV PCM de 16 bits dentro de `microfono_bt`. Desde la raíz del repositorio, calcula el retardo relativo:

```
python .\evaluar_prueba.py .\microfono_bt\bt.wav --referencia .\microfono_bt\referencia.wav
```

Un retardo positivo indica que Bluetooth llega después de la referencia. La medida incluye el retardo de la ruta de referencia; usa el mismo montaje en todas las repeticiones. Una correlación baja significa que las pistas no se parecen lo suficiente y no debe reportarse la latencia.

**6.5 Saturación y continuidad**

- Para el WAV de una prueba, ejecuta desde la raíz `python .\evaluar_prueba.py .\captura.wav`. El porcentaje cercano al máximo digital debe ser bajo.
- Por USB, `grabar_audio.py` detecta bloques faltantes en su número de secuencia y guarda la continuidad en `*_continuidad_usb.json`.
- Por Bluetooth, el monitor ESP-IDF imprime `METRICAS` cada segundo: saturación I2S/salida, errores I2S, bytes descartados por la cola, bytes HFP rellenados con silencio y estado de conexión. Guarda el log por separado por prueba y pásalo con `--firmware-log`.
- Los bytes HFP rellenados con silencio indican falta de audio en la cola local; no son una medida directa de pérdidas de radio.

**6.6 Estabilidad**

Deja el sistema grabando 30 minutos. No debe reiniciarse ni desconectarse; revísalo en el monitor de VS Code.

**Lista final: proyecto funcionando**

- [ ] Los dos micrófonos responden (Etapa 1).
- [ ] La captura USB tiene continuidad reportada y saturación baja (Etapa 3).
- [ ] El ESP32 se empareja y transmite por Bluetooth (Etapa 5).
- [ ] La captura Bluetooth tiene métricas de conexión/cola y saturación documentadas (Etapa 5).
- [ ] Tabla 6.1 completa, con espectrogramas guardados.
- [ ] Pruebas de inteligibilidad, alcance, latencia y estabilidad anotadas y repetibles.

## Solución de problemas

| Problema | Etapa | Qué hacer |
| --- | --- | --- |
| Error `ESP_I2S.h: No such file` | 1, 2 | Instala el paquete esp32 versión 3.x en el Gestor de tarjetas |
| Se queda en `Connecting.....` | 1, 2, 4 | Mantén presionado BOOT hasta que avance la carga |
| Puerto COM ocupado o "Access denied" | 2, 3, 4 | Cierra el Monitor Serie, el Serial Plotter y el monitor de VS Code |
| Una línea del plotter queda en 0 | 1 | Revisa SD, VDD, GND y L/R de ese micrófono |
| Las líneas aparecen invertidas | 1 | Revisa los pines L/R. Si están bien, el canal izquierdo y derecho están al revés: intercambia `m1` y `m2` en los códigos 3 y 6 |
| `filtro_ruido.h: No such file` | 2, 4 | El archivo debe estar en la misma carpeta que el `.ino`, o en `main` en ESP-IDF, con el nombre exacto |
| "No llegan datos" en `grabar_audio.py` | 3 | Revisa el número de COM y que el código 3 esté cargado |
| `python` o `pip` no se reconoce | 0, 3 | Reinstala Python marcando "Add python.exe to PATH" |
| La voz filtrada se corta al inicio de las palabras | 3, 5 | En `arduino\grabador_serial\filtro_ruido.h`, baja `FR_RELACION_VOZ` gradualmente (por ejemplo, de 2.5 a 2.0) o `FR_ON_MS` (de 64 a 48); esto puede dejar pasar más ruido |
| Sigue pasando mucho ruido durante el silencio | 3, 5 | Si `Estado` indica silencio, prueba bajar `FR_GANANCIA_GATE` de 0.05 a 0.02. Si los golpes activan voz, sube `FR_RELACION_VOZ` o `FR_ON_MS` gradualmente; comprueba que la voz cercana aún se detecte |
| La voz filtrada suena saturada | 3, 5 | Baja `FR_GANANCIA` gradualmente (por ejemplo, de 0.5 a 0.35) |
| Error de compilación en ESP-IDF sobre Bluetooth o HFP | 4 | Borra `sdkconfig` y `build`, compila de nuevo y revisa menuconfig (4.2). Si sigue, copia el error completo y pídeme la corrección |
| MicESP32 no aparece al buscar | 5 | Revisa que el monitor diga "Listo" y reinicia el ESP32 con el botón EN |
| Emparejado, pero no aparece como micrófono | 5 | Panel de control → Dispositivos e impresoras → MicESP32 → Propiedades → Servicios: marca "Telefonía manos libres". Si no, quita el dispositivo y empareja de nuevo |
| Audacity graba silencio | 5 | Revisa que el monitor diga "Audio abierto". Si no aparece, desconecta y reconecta MicESP32 desde Bluetooth de Windows |
| El audio por Bluetooth se corta | 5, 6 | Acércate al PC (menos de 5 m) y sin obstáculos |
