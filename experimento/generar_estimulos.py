"""
generar_estimulos.py - Crea los audios de prueba del experimento (siempre iguales)

Uso:
    python generar_estimulos.py frase.wav            # con tu frase grabada una sola vez
    python generar_estimulos.py --sintetica          # voz sintetica, para probar el montaje

Opciones:
    --ruido blanco|rosa   tipo de ruido (por defecto: rosa, mas parecido al ruido real)
    --inicio 4.0          segundos de solo ruido antes de la frase
    --semilla 1234        semilla del ruido: misma semilla = mismo ruido

Crea la carpeta estimulos/ con:
    estimulo_estereo.wav  izquierdo = frase, derecho = ruido (dos parlantes)
    estimulo_voz.wav      solo la frase (si el ruido sale de otro equipo)
    ruido_continuo.wav    60 s de ruido para reproducir en otro equipo
    estimulo.json         tiempos y parametros (los usa experimento.py)

Requisitos:  pip install numpy scipy
"""
import argparse
import json
import os

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

FS = 48000          # frecuencia de reproduccion
RMS_DBFS = -20.0    # nivel de referencia de la frase y del ruido


def a_rms(x, dbfs):
    rms = np.sqrt(np.mean(x ** 2)) + 1e-12
    return x * (10 ** (dbfs / 20) / rms)


def desvanecer(x, ms=50):
    n = int(FS * ms / 1000)
    rampa = np.linspace(0, 1, n)
    x = x.copy()
    x[:n] *= rampa
    x[-n:] *= rampa[::-1]
    return x


def cargar_frase(ruta):
    fs, x = wavfile.read(ruta)
    x = x.astype(np.float64)
    if x.ndim == 2:
        x = x.mean(axis=1)
    x /= np.max(np.abs(x)) + 1e-12
    if fs != FS:
        g = np.gcd(int(fs), FS)
        x = resample_poly(x, FS // g, int(fs) // g)
    # recortar silencios del inicio y del final
    env = np.convolve(np.abs(x), np.ones(480) / 480, mode="same")
    activo = np.where(env > 0.02 * env.max())[0]
    x = x[max(activo[0] - 2400, 0): activo[-1] + 2400]
    return desvanecer(x, 20)


def frase_sintetica(segundos=6.0):
    """Senal con forma de voz (armonicos + silabas) para probar el montaje."""
    t = np.arange(int(FS * segundos)) / FS
    f0 = 140 + 20 * np.sin(2 * np.pi * 0.5 * t)
    fase = 2 * np.pi * np.cumsum(f0) / FS
    x = sum(np.sin(k * fase) / k for k in range(1, 20))
    silabas = np.clip(np.sin(2 * np.pi * 3.5 * t), 0, None) ** 0.6
    pausas = (np.sin(2 * np.pi * 0.4 * t) > -0.6).astype(float)
    return desvanecer(x * silabas * pausas, 20)


def generar_ruido(n, tipo, semilla):
    rng = np.random.default_rng(semilla)
    blanco = rng.standard_normal(n)
    if tipo == "blanco":
        return blanco
    espectro = np.fft.rfft(blanco)
    f = np.fft.rfftfreq(n, 1 / FS)
    f[0] = f[1]
    return np.fft.irfft(espectro / np.sqrt(f), n)   # ruido rosa (1/f)


def guardar(nombre, x):
    wavfile.write(nombre, FS, np.clip(x * 32767, -32768, 32767).astype(np.int16))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("frase", nargs="?", help="WAV con la frase grabada una vez")
    p.add_argument("--sintetica", action="store_true")
    p.add_argument("--ruido", choices=["blanco", "rosa"], default="rosa")
    p.add_argument("--inicio", type=float, default=4.0)
    p.add_argument("--final", type=float, default=1.0)
    p.add_argument("--semilla", type=int, default=1234)
    p.add_argument("--carpeta", default="estimulos")
    a = p.parse_args()

    if a.frase:
        voz, origen = cargar_frase(a.frase), os.path.basename(a.frase)
    elif a.sintetica:
        voz, origen = frase_sintetica(), "sintetica"
    else:
        p.error("indica el archivo de la frase o usa --sintetica")

    voz = a_rms(voz, RMS_DBFS)
    n_ini, n_fin = int(a.inicio * FS), int(a.final * FS)
    total = n_ini + len(voz) + n_fin
    ruido = desvanecer(a_rms(generar_ruido(total, a.ruido, a.semilla), RMS_DBFS))
    canal_voz = np.concatenate([np.zeros(n_ini), voz, np.zeros(n_fin)])

    pico = max(np.max(np.abs(canal_voz)), np.max(np.abs(ruido)))
    escala = 0.89 / pico if pico > 0.89 else 1.0   # evita saturar
    canal_voz, ruido = canal_voz * escala, ruido * escala

    os.makedirs(a.carpeta, exist_ok=True)
    guardar(os.path.join(a.carpeta, "estimulo_estereo.wav"), np.stack([canal_voz, ruido], 1))
    guardar(os.path.join(a.carpeta, "estimulo_voz.wav"), np.stack([canal_voz, np.zeros(total)], 1))
    continuo = a_rms(generar_ruido(60 * FS, a.ruido, a.semilla + 1), RMS_DBFS) * escala
    guardar(os.path.join(a.carpeta, "ruido_continuo.wav"), desvanecer(continuo))

    info = {
        "fs": FS,
        "inicio_voz_s": a.inicio,
        "duracion_voz_s": round(len(voz) / FS, 3),
        "duracion_total_s": round(total / FS, 3),
        "ruido": a.ruido,
        "semilla": a.semilla,
        "frase": origen,
        "nivel_referencia_dbfs": RMS_DBFS,
        "escala": round(escala, 4),
    }
    with open(os.path.join(a.carpeta, "estimulo.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
    print(f"Estimulos creados en '{a.carpeta}/'")
    print(f"  Frase: {info['duracion_voz_s']} s, empieza en {a.inicio} s; total {info['duracion_total_s']} s")


if __name__ == "__main__":
    main()
