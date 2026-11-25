# Protocolo experimental: filtro desactivado vs activado

Objetivo: medir cuánto mejora la relación señal/ruido (SNR) el filtro, con la **misma frase, la misma posición y el mismo volumen de ruido** en todas las tomas, de forma que cualquiera pueda repetir el experimento y obtener resultados comparables.

## Cómo se garantiza que sea reproducible

| Variable | Cómo se mantiene fija |
|---|---|
| Frase | Se graba **una sola vez** y siempre se reproduce el mismo archivo por un parlante (nadie habla en vivo) |
| Ruido | Archivo generado con semilla fija: siempre es exactamente el mismo ruido |
| Volumen | Volumen de Windows fijo y niveles medidos con sonómetro, guardados en los resultados |
| Posición | Parlantes y micrófonos fijados con cinta en posiciones marcadas y anotadas |
| Filtro sin vs con | El ESP32 entrega **el mismo sonido** en dos versiones a la vez: sin filtro (canal izquierdo) y con filtro (canal derecho) |
| Estado del filtro | Se reinicia antes de cada toma |
| Variación | Cada condición se repite varias veces (5 por defecto), en orden aleatorio |

## Archivos

| Archivo | Entorno | Qué hace |
|---|---|---|
| `experimento_esp32/experimento_esp32.ino` | Arduino IDE | Firmware de medición: envía por USB el audio sin filtro y con filtro, y reinicia el filtro cuando el PC lo pide |
| `experimento_esp32/filtro_ruido.h` | Arduino IDE | El filtro (el mismo del proyecto) |
| `generar_estimulos.py` | Python | Crea los audios de prueba: frase + ruido |
| `experimento.py` | Python | Corre todo el experimento: calibra, reproduce, graba, mide y grafica |
| `config_experimento.json` | Editor de texto | Puerto, condiciones de ruido, repeticiones y datos del montaje |

Instalar una vez:

```
pip install pyserial numpy scipy matplotlib sounddevice
```

## Montaje

```
   Parlante IZQUIERDO (voz)          Parlante DERECHO (ruido)
          │ 10 cm                            │ 100 cm
          ▼                                  ▼
      [Mic 1] ←── 10 cm ──→ [Mic 2]  (Mic 2 mirando hacia otro lado)
                    │
                 ESP32 ── USB ── PC
```

- Usa **parlantes estéreo de PC** (o dos parlantes con un cable divisor): el izquierdo hace de "boca" y el derecho de fuente de ruido. Los parlantes internos de un portátil no sirven, porque están juntos.
- Marca con cinta la posición de cada parlante y micrófono y anota las distancias en `config_experimento.json` (sección `montaje`).
- Sin parlantes estéreo: pon `"modo_ruido": "externo"` y reproduce `ruido_continuo.wav` desde un celular o parlante Bluetooth fijo a 1 m. El script te pedirá ajustar ese volumen en cada condición.
- Haz el experimento en un cuarto sin otros ruidos (puerta cerrada, ventilador apagado).

## Procedimiento

**1. Grabar la frase (una sola vez)**

Graba con el celular o Audacity una frase de 5 a 8 segundos, por ejemplo: *"El sistema captura la voz y reduce el ruido del ambiente de forma inalámbrica"*. Guárdala como `frase.wav` en la carpeta del experimento.

**2. Generar los estímulos**

```
python generar_estimulos.py frase.wav
```

Crea la carpeta `estimulos/`. Para probar el montaje antes de grabar la frase: `python generar_estimulos.py --sintetica`.

**3. Cargar el firmware**

En Arduino IDE abre `experimento_esp32/experimento_esp32.ino` (con `filtro_ruido.h` en la misma carpeta) y súbelo. Cierra el Monitor Serie.

**4. Configurar**

En `config_experimento.json` cambia `"puerto"` por tu COM. Deja el volumen de Windows en el valor anotado en `montaje` y no lo cambies durante el experimento.

**5. Correr el experimento**

```
python experimento.py config_experimento.json
```

El script hace todo en orden:

1. **Calibración:** reproduce la frase sola y luego el ruido de cada condición. Mide con el sonómetro junto al micrófono 1 y escribe el valor cuando te lo pida. Si un nivel no se acerca al objetivo de la condición, ajusta `ganancia_ruido_db` en el archivo de configuración y vuelve a empezar.
2. **Medición:** reproduce el estímulo completo (4 s de solo ruido y luego la frase) en cada toma, en orden aleatorio. No hables ni muevas nada mientras dura.
3. **Análisis:** calcula las métricas y genera tablas y gráficas.

Duración aproximada: 3 condiciones × 5 tomas × 13 s ≈ 4 minutos de medición.

**6. Volver a analizar sin repetir mediciones (opcional)**

```
python experimento.py --analizar resultados/2026-11-25_1530
```

## Qué se mide en cada toma

Los tramos son fijos porque el estímulo siempre es el mismo:
- **Solo ruido:** de 2.0 s a 3.9 s del estímulo. Los primeros 2 s se dejan para que el filtro se adapte.
- **Voz + ruido:** desde 0.3 s después de que empieza la frase hasta que termina.

| Métrica | Significado |
|---|---|
| `snr_sin_db` / `snr_con_db` | SNR con el filtro desactivado / activado |
| `mejora_db` | SNR con filtro − SNR sin filtro. **El resultado principal** |
| `reduccion_ruido_db` | Cuánto baja el ruido de fondo |
| `cambio_voz_db` | Cuánto cambia el nivel de la voz. Cerca de 0 es mejor: el filtro no se "come" la voz |
| `saturacion_pct` | % de muestras saturadas. Debe ser 0; si no, baja el volumen |
| `muestras_ok` | `False` si se perdieron datos por USB. Repite esa toma |

## Resultados que se generan

En `resultados/<fecha_hora>/`:

| Archivo | Contenido |
|---|---|
| `tomas/*.wav` | Cada toma en estéreo: izquierdo sin filtro, derecho con filtro |
| `mediciones.csv` | Una fila por toma con todas las métricas |
| `resumen.csv` | Por condición: media, desviación estándar, intervalo de confianza del 95 % de la mejora y valor p de la prueba t pareada |
| `grafica_snr.png` | Barras de SNR sin y con filtro por condición, con barras de error |
| `espectrograma_<condición>.png` | Espectrogramas sin y con filtro, con la misma escala de color y los tramos medidos marcados |
| `registro.json` y `config_usada.json` | Todo lo necesario para repetir el experimento: estímulo, niveles medidos, montaje y orden de las tomas |

## Qué reportar en el informe

1. El montaje: foto, distancias y volumen de Windows.
2. Los niveles de voz y de ruido medidos con el sonómetro.
3. La tabla `resumen.csv`, presentando la mejora como media ± desviación (n = 5), con su IC 95 % y el valor p.
4. `grafica_snr.png` y un espectrograma representativo.
5. Un par de tomas de audio, sin y con filtro, para que se escuche la diferencia.

## Lista de verificación antes de medir

- [ ] Firmware `experimento_esp32.ino` cargado y Monitor Serie cerrado
- [ ] Parlantes y micrófonos en las marcas; distancias anotadas en la configuración
- [ ] Volumen de Windows en el valor anotado
- [ ] Cuarto en silencio
- [ ] `estimulos/` generada con la frase definitiva
