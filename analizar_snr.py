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
    if t < 10:
        raise ValueError("Se necesitan al menos 10 ventanas de audio para estimar la SNR")
    e = np.sort(np.mean(x[: t * n].reshape(t, n) ** 2, axis=1))
    k = max(1, t // 10)
    p_voz, p_ruido = e[-k:].mean(), e[:k].mean()
    if p_ruido < 1.0 or p_voz <= p_ruido:
        return None, p_ruido
    return 10 * np.log10((p_voz - p_ruido) / p_ruido), p_ruido


def formato_db(valor):
    return f"{valor:6.1f} dB" if valor is not None else "no estimable"


def main():
    if len(sys.argv) == 3:
        fs, sin = leer(sys.argv[1])
        fs_con, con = leer(sys.argv[2])
        if fs != fs_con:
            raise ValueError("Las grabaciones deben tener la misma frecuencia de muestreo")
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
    print(f"SNR aprox. sin filtro : {formato_db(snr_sin)}")
    print(f"SNR aprox. con filtro : {formato_db(snr_con)}")
    if snr_sin is not None and snr_con is not None:
        print(f"Mejora                : {snr_con - snr_sin:6.1f} dB")
    else:
        print("Mejora                : no estimable (ruido muy bajo o tramos sin voz)")
    if ruido_sin >= 1.0 and ruido_con >= 1.0:
        print(f"Reduccion del ruido de fondo: {10 * np.log10(ruido_sin / ruido_con):.1f} dB")
    else:
        print("Reduccion del ruido de fondo: no estimable")

    fig, ejes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for eje, x, titulo in [(ejes[0], sin, f"Sin filtro (SNR {formato_db(snr_sin)})"),
                           (ejes[1], con, f"Con filtro (SNR {formato_db(snr_con)})")]:
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
