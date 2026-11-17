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
