import argparse
import csv
import json
import re
import sys
import wave
from pathlib import Path

import numpy as np
from scipy.signal import correlate, resample_poly

METRICAS_FW = (
    "i2s_muestras",
    "i2s_errores",
    "clip_m1",
    "clip_m2",
    "clip_salida",
    "muestras_salida",
    "cola_perdida_bytes",
    "hfp_solicitado_bytes",
    "hfp_silencio_bytes",
    "hfp_audio_conexiones",
    "hfp_audio_desconexiones",
)


def leer_wav(nombre):
    with wave.open(str(nombre), "rb") as wav:
        if wav.getsampwidth() != 2:
            raise ValueError(f"{nombre}: se requiere WAV PCM de 16 bits")
        canales = wav.getnchannels()
        frecuencia = wav.getframerate()
        audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    if canales > 1:
        audio = audio.reshape(-1, canales)
    if len(audio) == 0:
        raise ValueError(f"{nombre}: el WAV no contiene muestras")
    return frecuencia, audio.astype(np.float64), canales


def medir_saturacion(audio):
    if audio.ndim == 1:
        audio = audio[:, None]
    canales = []
    for indice in range(audio.shape[1]):
        muestras = audio[:, indice]
        saturadas = np.count_nonzero(np.abs(muestras) >= 32760)
        canales.append({
            "canal": indice + 1,
            "pico_abs": int(np.max(np.abs(muestras))) if len(muestras) else 0,
            "muestras_cercanas_full_scale": int(saturadas),
            "saturacion_pct": 100.0 * saturadas / max(1, len(muestras)),
        })
    return canales


def estimar_latencia(referencia, bluetooth, max_segundos):
    fs_ref, ref, canales_ref = leer_wav(referencia)
    fs_bt, bt, canales_bt = leer_wav(bluetooth)
    if canales_ref > 1:
        ref = ref.mean(axis=1)
    if canales_bt > 1:
        bt = bt.mean(axis=1)

    fs_comun = 8000
    ref = resample_poly(ref, fs_comun, fs_ref)
    bt = resample_poly(bt, fs_comun, fs_bt)
    max_muestras = int(max_segundos * fs_comun)
    ref = ref[:max_muestras]
    bt = bt[:max_muestras]
    ref -= ref.mean()
    bt -= bt.mean()
    if np.linalg.norm(ref) == 0 or np.linalg.norm(bt) == 0:
        raise ValueError("No hay señal suficiente para estimar la latencia")

    correlacion = correlate(bt, ref, mode="full", method="fft")
    lags = np.arange(-len(ref) + 1, len(bt))
    limite = int(max_segundos * fs_comun)
    seleccion = np.abs(lags) <= limite
    lags = lags[seleccion]
    cross = correlacion[seleccion]
    inicio_ref = np.maximum(0, -lags)
    fin_ref = np.minimum(len(ref), len(bt) - lags)
    muestras_comunes = fin_ref - inicio_ref
    minimo_comun = min(fs_comun, min(len(ref), len(bt)) // 2)
    validos = muestras_comunes >= minimo_comun
    if not np.any(validos):
        raise ValueError("Las grabaciones no tienen suficiente tramo comun")


    suma_ref = np.concatenate(([0.0], np.cumsum(ref * ref)))
    suma_bt = np.concatenate(([0.0], np.cumsum(bt * bt)))
    energia_ref = suma_ref[fin_ref] - suma_ref[inicio_ref]
    energia_bt = suma_bt[fin_ref + lags] - suma_bt[inicio_ref + lags]
    denominador = np.sqrt(np.maximum(energia_ref * energia_bt, 1e-12))
    normalizada = np.abs(cross) / denominador
    normalizada[~validos] = 0.0
    indice = int(np.argmax(normalizada))
    lag = int(lags[indice])
    confianza = float(normalizada[indice])
    return {
        "latencia_estimada_ms": 1000.0 * lag / fs_comun,
        "retardo_bt_muestras": lag,
        "correlacion_normalizada": confianza,
        "latencia_confiable": confianza >= 0.2,
    }


def leer_metricas_firmware(nombre):
    patron = re.compile(r"METRICAS\s+(.+)")
    registros = []
    with open(nombre, encoding="utf-8", errors="replace") as archivo:
        for linea in archivo:
            coincidencia = patron.search(linea)
            if not coincidencia:
                continue
            datos = {}
            for campo in coincidencia.group(1).split():
                if "=" not in campo:
                    continue
                clave, valor = campo.split("=", 1)
                try:
                    datos[clave] = float(valor) if "." in valor else int(valor)
                except ValueError:
                    continue
            if datos:
                registros.append(datos)
    if not registros:
        raise ValueError(f"No se encontraron líneas METRICAS en {nombre}")
    if len(registros) < 2:
        raise ValueError("El log debe contener al menos dos líneas METRICAS")

    inicio, fin = registros[0], registros[-1]
    deltas = {}
    for clave in METRICAS_FW:
        valores = [registro[clave] for registro in registros if clave in registro]
        if len(valores) >= 2:
            total = 0
            reinicios = 0
            for anterior, actual in zip(valores, valores[1:]):
                if actual >= anterior:
                    total += actual - anterior
                else:
                    total += actual
                    reinicios += 1
            deltas[clave + "_en_prueba"] = total
            deltas["reinicios_contador_firmware"] = max(
                deltas.get("reinicios_contador_firmware", 0), reinicios
            )
    deltas["registros_metricas_firmware"] = len(registros)
    deltas["estado_conectado_final"] = fin.get("conectado")
    deltas["frecuencia_bluetooth_hz"] = fin.get("fs_bt")
    return deltas


def main():
    parser = argparse.ArgumentParser(
        description="Mide saturación, continuidad Bluetooth y latencia en WAV."
    )
    parser.add_argument("wav", help="Grabación WAV PCM de 16 bits")
    parser.add_argument("--referencia", help="WAV de referencia grabado simultáneamente")
    parser.add_argument("--firmware-log", help="Log ESP-IDF guardado como texto")
    parser.add_argument("--distancia-m", "--distance-m", dest="distancia_m",
                        type=float, help="Distancia ESP32-PC durante la prueba")
    parser.add_argument("--correlacion-s", type=float, default=20.0)
    parser.add_argument("--csv", default="resultados_pruebas.csv")
    args = parser.parse_args()
    if args.distancia_m is not None and args.distancia_m <= 0:
        parser.error("--distancia-m debe ser mayor que cero")
    if args.correlacion_s <= 0:
        parser.error("--correlacion-s debe ser mayor que cero")

    frecuencia, audio, canales = leer_wav(args.wav)
    metricas = {
        "archivo": str(args.wav),
        "frecuencia_hz": frecuencia,
        "canales": canales,
        "duracion_s": len(audio) / frecuencia,
        "distancia_m": args.distancia_m,
        "saturacion": medir_saturacion(audio),
    }
    if args.referencia:
        metricas.update(estimar_latencia(args.referencia, args.wav, args.correlacion_s))
    if args.firmware_log:
        metricas.update(leer_metricas_firmware(args.firmware_log))

    salida_json = Path(args.wav).with_name(Path(args.wav).stem + "_evaluacion.json")
    with open(salida_json, "w", encoding="utf-8") as informe:
        json.dump(metricas, informe, ensure_ascii=False, indent=2)

    print(f"Duración: {metricas['duracion_s']:.2f} s")
    for canal in metricas["saturacion"]:
        print(
            f"Canal {canal['canal']}: pico={canal['pico_abs']}/32767, "
            f"cercano a saturación={canal['saturacion_pct']:.4f}%"
        )
    if args.referencia:
        print(
            f"Retardo BT respecto a referencia: "
            f"{metricas['latencia_estimada_ms']:.2f} ms "
            f"(correlación={metricas['correlacion_normalizada']:.3f}, "
            f"{'confiable' if metricas['latencia_confiable'] else 'no confiable'})"
        )
    if args.firmware_log:
        for clave in (
            "cola_perdida_bytes_en_prueba",
            "hfp_silencio_bytes_en_prueba",
            "hfp_audio_conexiones_en_prueba",
            "hfp_audio_desconexiones_en_prueba",
            "i2s_errores_en_prueba",
            "estado_conectado_final",
        ):
            if clave in metricas:
                print(f"{clave}: {metricas[clave]}")
    print(f"Informe JSON: {salida_json}")

    fila = {
        "archivo": metricas["archivo"],
        "duracion_s": round(metricas["duracion_s"], 3),
        "distancia_m": args.distancia_m,
        "saturacion_max_pct": max(
            (canal["saturacion_pct"] for canal in metricas["saturacion"]),
            default=0.0,
        ),
        "latencia_ms": metricas.get("latencia_estimada_ms", ""),
        "correlacion": metricas.get("correlacion_normalizada", ""),
        "bt_cola_perdida_bytes": metricas.get("cola_perdida_bytes_en_prueba", ""),
        "bt_underflow_bytes": metricas.get("hfp_silencio_bytes_en_prueba", ""),
        "bt_audio_conexiones": metricas.get("hfp_audio_conexiones_en_prueba", ""),
        "bt_audio_desconexiones": metricas.get("hfp_audio_desconexiones_en_prueba", ""),
        "i2s_errores": metricas.get("i2s_errores_en_prueba", ""),
        "bt_conectado_final": metricas.get("estado_conectado_final", ""),
    }
    existe = Path(args.csv).exists()
    if existe:
        with open(args.csv, newline="", encoding="utf-8") as archivo:
            encabezado = next(csv.reader(archivo), [])
        if encabezado != list(fila.keys()):
            raise ValueError(
                f"El CSV {args.csv} tiene columnas incompatibles; usa otro nombre con --csv"
            )
    with open(args.csv, "a", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=fila.keys())
        if not existe:
            escritor.writeheader()
        escritor.writerow(fila)
    print(f"Fila añadida a {args.csv}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, wave.Error) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(2)
