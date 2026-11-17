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
