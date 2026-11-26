import struct
import sys
import json
import time
import wave

import numpy as np

FS = 16000
BAUDIOS = 921600
CABECERA_BYTES = 8


def extraer_bloques(buf):
    bloques = []
    while True:
        i = buf.find(b"\xaa\x55")
        if i < 0:
            return bloques, buf[-1:]
        if len(buf) < i + CABECERA_BYTES:
            return bloques, buf[i:]
        n = struct.unpack_from("<H", buf, i + 2)[0]
        if n == 0 or n > 512:
            buf = buf[i + 2:]
            continue
        secuencia = struct.unpack_from("<I", buf, i + 4)[0]
        fin = i + CABECERA_BYTES + n * 4
        if len(buf) < fin:
            return bloques, buf[i:]
        muestras = np.frombuffer(
            bytes(buf[i + CABECERA_BYTES:fin]), dtype="<i2"
        ).reshape(-1, 2)
        bloques.append((secuencia, muestras))
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
        secuencia_anterior = None
        bloques_perdidos = 0
        bloques_duplicados = 0
        bloques_fuera_orden = 0
        inicio = time.perf_counter()
        while total < objetivo:
            datos = ser.read(4096)
            if not datos:
                print("No llegan datos. Revisa el puerto y que la Prueba 2 este cargada.")
                return
            nuevos, buf = extraer_bloques(buf + datos)
            buf = bytearray(buf)
            for secuencia, muestras in nuevos:
                if secuencia_anterior is not None:
                    delta = (secuencia - secuencia_anterior) & 0xFFFFFFFF
                    if delta == 0:
                        bloques_duplicados += 1
                        continue
                    if delta >= 0x80000000:
                        bloques_fuera_orden += 1
                        continue
                    bloques_perdidos += delta - 1
                secuencia_anterior = secuencia
                bloques.append(muestras)
                total += len(muestras)
            seg = total // FS
            if seg != ultimo:
                print(f"  {seg} s", end="\r")
                ultimo = seg
        duracion_captura = time.perf_counter() - inicio

    audio = np.concatenate(bloques)[:objetivo]
    guardar_wav(archivo, audio)
    base = archivo.rsplit(".", 1)[0]
    guardar_wav(base + "_original.wav", audio[:, 0])
    guardar_wav(base + "_filtrada.wav", audio[:, 1])
    total_bloques = len(bloques)
    continuidad = 100.0 * total_bloques / max(
        1, total_bloques + bloques_perdidos
    )
    metricas = {
        "archivo": archivo,
        "frecuencia_hz": FS,
        "muestras_objetivo": objetivo,
        "duracion_audio_s": len(audio) / FS,
        "duracion_captura_s": round(duracion_captura, 3),
        "bloques_recibidos": total_bloques,
        "bloques_perdidos_secuencia": bloques_perdidos,
        "bloques_duplicados": bloques_duplicados,
        "bloques_fuera_orden": bloques_fuera_orden,
        "continuidad_usb_pct": round(continuidad, 4),
    }
    with open(base + "_continuidad_usb.json", "w", encoding="utf-8") as informe:
        json.dump(metricas, informe, ensure_ascii=False, indent=2)
    print(f"\nListo: {archivo}, {base}_original.wav y {base}_filtrada.wav")
    print(
        f"Continuidad USB: {continuidad:.3f}% "
        f"({bloques_perdidos} perdidos, {bloques_duplicados} duplicados, "
        f"{bloques_fuera_orden} fuera de orden). "
        f"Informe: {base}_continuidad_usb.json"
    )


if __name__ == "__main__":
    main()
