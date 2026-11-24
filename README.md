# Captura de voz inalámbrica con ESP32

Este repositorio contiene los archivos de software descritos en las guías de
hardware y software. Los pines son los de la conexión documentada:

| Señal | ESP32 |
| --- | --- |
| I2S SCK/BCLK | GPIO 26 |
| I2S WS/LRCLK | GPIO 25 |
| I2S SD/DOUT de los INMP441 | GPIO 33 |
| Botón BOOT | GPIO 0 |
| LED de estado | GPIO 2 |

## Archivos

- `arduino\prueba_microfonos\prueba_microfonos.ino`: prueba los dos micrófonos
  en vivo. Las líneas incluyen RMS de ambos canales, relación entre
  micrófonos, piso de ruido, estado (`CALIBRANDO`, `VOZ` o `SILENCIO`) y picos.
- `arduino\grabador_serial\grabador_serial.ino` y
  `arduino\grabador_serial\filtro_ruido.h`: prueba el filtro y envía audio
  estéreo por USB (original a la izquierda, filtrado a la derecha).
- `grabar_audio.py` y `analizar_snr.py`: graban el flujo USB y comparan
  grabaciones WAV.
- `microfono_bt\`: firmware ESP-IDF para transmitir como micrófono Bluetooth
  manos libres (`MicESP32`).
- `requirements.txt`: dependencias de los scripts de PC.

## Probar por USB

1. Revisa las conexiones con `Guía de conexiones de hardware — Captura de voz
   inalámbrica con ESP32.md`. En especial, alimenta los micrófonos con 3V3,
   nunca VIN.
2. En Arduino IDE 2 instala `esp32 by Espressif Systems` 3.x y selecciona
   **ESP32 Dev Module** y el puerto COM de la placa.
3. Abre y carga `arduino\prueba_microfonos\prueba_microfonos.ino`. Abre el
   Serial Plotter a 115200 baudios y confirma que cada micrófono mueve su
   propia línea.
4. Cierra el Plotter. Abre y carga
   `arduino\grabador_serial\grabador_serial.ino`. No abras el Monitor Serie ni
   el Plotter mientras transmite audio binario.
5. Instala las dependencias desde una terminal en esta carpeta:

   ```text
   python -m pip install -r requirements.txt
   ```

6. Graba (cambia `COM3` por el puerto real):

   ```text
   python grabar_audio.py COM3 15 prueba1.wav
   python analizar_snr.py prueba1.wav
   ```

## Probar por Bluetooth

El firmware de `microfono_bt\` requiere VS Code con la extensión ESP-IDF y
ESP-IDF 5.x. Abre esa carpeta como proyecto, selecciona el objetivo `esp32`,
configura el puerto y compila/carga desde la extensión. Se necesita un ESP32
clásico con Bluetooth BR/EDR; ESP32-S2, ESP32-S3 y ESP32-C3 no soportan
Bluetooth Classic HFP. El audio Bluetooth requiere emparejar `MicESP32` y
seleccionarlo como entrada de sonido en Windows.

El botón BOOT alterna el filtro y el LED GPIO 2 indica su estado. Cierra los
monitores serie antes de cambiar entre Arduino y ESP-IDF para liberar el puerto
COM.

Para instrucciones completas, instalación, procedimiento experimental y
solución de problemas, consulta las dos guías `.md` de este directorio.
