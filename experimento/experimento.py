"""
experimento.py - Comparacion experimental reproducible: filtro DESACTIVADO vs ACTIVADO

Mantiene fijos la frase, la posicion y el volumen del ruido:
  - La frase y el ruido salen siempre de los mismos archivos (generar_estimulos.py).
  - Los niveles se calibran con un sonometro y quedan registrados.
  - El ESP32 (experimento_esp32.ino) entrega el MISMO sonido sin filtro y con filtro
    a la vez, y el filtro se reinicia antes de cada toma.
  - Cada condicion se repite varias veces para medir la variacion.

Uso:
    python experimento.py config_experimento.json            # correr el experimento
    python experimento.py --analizar resultados/2026-11-25_1530  # volver a analizar

Requisitos:  pip install pyserial numpy scipy matplotlib sounddevice
Cierra el Monitor Serie de Arduino antes de empezar.
"""
import csv
import datetime
import json
import os
import random
import shutil
import struct
import sys
import threading
import time

import numpy as np
from scipy.io import wavfile

FS_ESP32 = 16000     # frecuencia del audio que envia el ESP32
BAUDIOS = 921600
PRE_GRAB = 0.5       # s que se graba antes de reproducir
POST_GRAB = 0.7      # s que se sigue grabando despues
APRENDIZAJE = 2.0    # s de ruido que se dejan para que el filtro se adapte


# ------------------------------------------------------------------ captura
def extraer_bloques(buf):
    """Separa los bloques que envia el ESP32: 0xAA 0x55, cantidad, muestras."""
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


class Grabador:
    """Lee el audio del ESP32 en segundo plano mientras el PC reproduce el estimulo."""

    def __init__(self, puerto):
        import serial
        self.ser = serial.Serial(puerto, BAUDIOS, timeout=0.1)

    def reiniciar_filtro(self):
        self.ser.write(b"r")
        time.sleep(0.5)
        self.ser.reset_input_buffer()

    def iniciar(self):
        self.bloques, self.buf = [], bytearray()
        self.parar = threading.Event()
        self.hilo = threading.Thread(target=self._leer, daemon=True)
        self.hilo.start()

    def _leer(self):
        while not self.parar.is_set():
            datos = self.ser.read(4096)
            if datos:
                nuevos, resto = extraer_bloques(self.buf + datos)
                self.buf = bytearray(resto)
                self.bloques += nuevos

    def detener(self):
        self.parar.set()
        self.hilo.join()
        if not self.bloques:
            return np.zeros((0, 2), dtype=np.int16)
        return np.concatenate(self.bloques)

    def cerrar(self):
        self.ser.close()


# ------------------------------------------------------------------ metricas
def ventanas(info):
    """Tramos de la grabacion (en s) donde se mide: solo ruido y voz + ruido."""
    ini, dur = info["inicio_voz_s"], info["duracion_voz_s"]
    ruido = (PRE_GRAB + APRENDIZAJE, PRE_GRAB + ini - 0.1)
    voz = (PRE_GRAB + ini + 0.3, PRE_GRAB + ini + dur)
    return ruido, voz


def potencia(x, t0, t1, fs=FS_ESP32):
    tramo = x[int(t0 * fs):int(t1 * fs)].astype(np.float64)
    return float(np.mean(tramo ** 2)) + 1e-9


def medir(audio, info):
    (r0, r1), (v0, v1) = ventanas(info)
    res = {}
    for canal, nombre in ((0, "sin"), (1, "con")):
        x = audio[:, canal]
        pn, pvr = potencia(x, r0, r1), potencia(x, v0, v1)
        pv = max(pvr - pn, 1e-9)
        res[f"snr_{nombre}_db"] = 10 * np.log10(pv / pn)
        res[f"_pn_{nombre}"], res[f"_pv_{nombre}"] = pn, pv
    res["mejora_db"] = res["snr_con_db"] - res["snr_sin_db"]
    res["reduccion_ruido_db"] = 10 * np.log10(res["_pn_sin"] / res["_pn_con"])
    res["cambio_voz_db"] = 10 * np.log10(res["_pv_con"] / res["_pv_sin"])
    res["saturacion_pct"] = 100 * float(np.mean(np.abs(audio[:, 0].astype(int)) >= 32000))
    return {k: round(v, 2) for k, v in res.items() if not k.startswith("_")}


# ------------------------------------------------------------------ analisis
def analizar(carpeta):
    with open(os.path.join(carpeta, "registro.json"), encoding="utf-8") as f:
        reg = json.load(f)
    info = reg["estimulo"]
    filas = []
    for toma in reg["tomas"]:
        fs, audio = wavfile.read(os.path.join(carpeta, "tomas", toma["archivo"]))
        fila = {**toma, **medir(audio, info)}
        fila["nivel_ruido_medido_db"] = reg["niveles_ruido_db"].get(toma["condicion"])
        fila["nivel_voz_medido_db"] = reg.get("nivel_voz_db")
        filas.append(fila)

    campos = ["orden", "condicion", "repeticion", "archivo", "fecha_hora",
              "nivel_voz_medido_db", "nivel_ruido_medido_db", "snr_sin_db", "snr_con_db",
              "mejora_db", "reduccion_ruido_db", "cambio_voz_db", "saturacion_pct", "muestras_ok"]
    with open(os.path.join(carpeta, "mediciones.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)

    resumen = resumir(filas, [c["nombre"] for c in reg["config"]["condiciones"]], reg, carpeta)
    graficar(carpeta, reg, resumen, info)
    return filas, resumen


def resumir(filas, condiciones, reg, carpeta):
    from scipy import stats
    resumen = []
    for cond in condiciones:
        g = [f for f in filas if f["condicion"] == cond]
        if not g:
            continue
        sin = np.array([f["snr_sin_db"] for f in g])
        con = np.array([f["snr_con_db"] for f in g])
        mej = con - sin
        n = len(g)
        fila = {
            "condicion": cond,
            "nivel_ruido_medido_db": reg["niveles_ruido_db"].get(cond),
            "n_tomas": n,
            "snr_sin_media_db": round(sin.mean(), 2),
            "snr_sin_desv_db": round(sin.std(ddof=1), 2) if n > 1 else 0.0,
            "snr_con_media_db": round(con.mean(), 2),
            "snr_con_desv_db": round(con.std(ddof=1), 2) if n > 1 else 0.0,
            "mejora_media_db": round(mej.mean(), 2),
            "mejora_desv_db": round(mej.std(ddof=1), 2) if n > 1 else 0.0,
            "reduccion_ruido_media_db": round(np.mean([f["reduccion_ruido_db"] for f in g]), 2),
            "cambio_voz_medio_db": round(np.mean([f["cambio_voz_db"] for f in g]), 2),
        }
        if n > 1:
            ic = stats.t.ppf(0.975, n - 1) * mej.std(ddof=1) / np.sqrt(n)
            fila["mejora_ic95_db"] = f"{mej.mean() - ic:.2f} a {mej.mean() + ic:.2f}"
            fila["p_valor_pareado"] = float(f"{stats.ttest_rel(con, sin).pvalue:.2e}") if mej.std() > 0 else 0.0
        resumen.append(fila)

    campos = list(dict.fromkeys(k for r in resumen for k in r))
    with open(os.path.join(carpeta, "resumen.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(resumen)

    print("\nRESUMEN (media +/- desviacion estandar)")
    print(f"{'Condicion':<16}{'n':>3}{'SNR sin':>14}{'SNR con':>14}{'Mejora':>14}{'Red. ruido':>12}")
    for r in resumen:
        print(f"{r['condicion']:<16}{r['n_tomas']:>3}"
              f"{r['snr_sin_media_db']:>8.1f} +/-{r['snr_sin_desv_db']:>4.1f}"
              f"{r['snr_con_media_db']:>8.1f} +/-{r['snr_con_desv_db']:>4.1f}"
              f"{r['mejora_media_db']:>8.1f} +/-{r['mejora_desv_db']:>4.1f}"
              f"{r['reduccion_ruido_media_db']:>10.1f} dB")
    return resumen


def graficar(carpeta, reg, resumen, info):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    etiquetas = [r["condicion"] + (f"\n({r['nivel_ruido_medido_db']} dB)" if r["nivel_ruido_medido_db"] else "")
                 for r in resumen]
    x = np.arange(len(resumen))
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x - 0.2, [r["snr_sin_media_db"] for r in resumen], 0.4,
           yerr=[r["snr_sin_desv_db"] for r in resumen], capsize=4, color="#9aa5b1", label="Filtro desactivado")
    ax.bar(x + 0.2, [r["snr_con_media_db"] for r in resumen], 0.4,
           yerr=[r["snr_con_desv_db"] for r in resumen], capsize=4, color="#2b6cb0", label="Filtro activado")
    for i, r in enumerate(resumen):
        ax.annotate(f"+{r['mejora_media_db']:.1f} dB", (i + 0.2, r["snr_con_media_db"] + r["snr_con_desv_db"]),
                    ha="center", va="bottom", fontsize=9, xytext=(0, 4), textcoords="offset points")
    ax.set_xticks(x, etiquetas)
    ax.set_ylabel("SNR (dB)")
    ax.set_title(f"SNR con y sin filtro ({resumen[0]['n_tomas']} tomas por condicion, media y desviacion)")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(carpeta, "grafica_snr.png"), dpi=150)
    plt.close(fig)

    (r0, r1), (v0, v1) = ventanas(info)
    for cond in [r["condicion"] for r in resumen]:
        toma = next(t for t in reg["tomas"] if t["condicion"] == cond)
        fs, audio = wavfile.read(os.path.join(carpeta, "tomas", toma["archivo"]))
        fig, ejes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
        tope = 10 * np.log10(np.max(np.abs(audio[:, 0].astype(float))) ** 2 + 1e-9)
        for eje, canal, titulo in ((ejes[0], 0, "Filtro desactivado"), (ejes[1], 1, "Filtro activado")):
            # misma escala de color en las dos graficas, para que se puedan comparar
            eje.specgram(audio[:, canal].astype(float), NFFT=512, Fs=fs, noverlap=384, cmap="magma",
                         vmin=tope - 100, vmax=tope - 20)
            eje.axvspan(r0, r1, color="white", alpha=0.12)
            eje.axvspan(v0, v1, color="cyan", alpha=0.08)
            eje.set_title(f"{cond}: {titulo}")
            eje.set_ylabel("Frecuencia (Hz)")
        ejes[1].set_xlabel("Tiempo (s)  [blanco: tramo de solo ruido, celeste: tramo de voz]")
        fig.tight_layout()
        fig.savefig(os.path.join(carpeta, f"espectrograma_{cond}.png"), dpi=150)
        plt.close(fig)
    print(f"Graficas guardadas en {carpeta}")


# ------------------------------------------------------------------ experimento
def leer_wav_float(ruta):
    fs, x = wavfile.read(ruta)
    return fs, x.astype(np.float32) / 32768.0


def pedir_nivel(mensaje):
    txt = input(mensaje + " (dB, Enter para omitir): ").strip().replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return None


def correr(ruta_config):
    import sounddevice as sd

    with open(ruta_config, encoding="utf-8") as f:
        cfg = json.load(f)
    est = cfg["carpeta_estimulos"]
    with open(os.path.join(est, "estimulo.json"), encoding="utf-8") as f:
        info = json.load(f)
    if info["inicio_voz_s"] < APRENDIZAJE + 0.6:
        sys.exit(f"inicio_voz_s debe ser al menos {APRENDIZAJE + 0.6} s (genera los estimulos con --inicio 4)")

    externo = cfg["modo_ruido"] == "externo"
    fs, estimulo = leer_wav_float(os.path.join(est, "estimulo_voz.wav" if externo else "estimulo_estereo.wav"))
    dispositivo = cfg.get("dispositivo_salida")

    carpeta = os.path.join(cfg["carpeta_resultados"], datetime.datetime.now().strftime("%Y-%m-%d_%H%M"))
    os.makedirs(os.path.join(carpeta, "tomas"), exist_ok=True)
    shutil.copy(ruta_config, os.path.join(carpeta, "config_usada.json"))

    def reproducir(senal):
        sd.play(senal, fs, device=dispositivo)
        sd.wait()

    # 1. Calibracion de niveles con el sonometro, junto al microfono 1
    print("\n=== CALIBRACION (sonometro junto al microfono 1) ===")
    input("Se reproducira solo la FRASE. Prepara el sonometro y pulsa Enter...")
    solo_voz = estimulo.copy()
    solo_voz[:, 1] = 0
    reproducir(solo_voz)
    nivel_voz = pedir_nivel("Nivel MAXIMO de la frase")

    niveles = {}
    for c in cfg["condiciones"]:
        if externo:
            input(f"\n[{c['nombre']}] Reproduce ruido_continuo.wav en el otro equipo con el volumen "
                  f"de esta condicion ({c.get('descripcion', '')}) y dejalo sonando. Enter...")
            time.sleep(2)
        else:
            input(f"\n[{c['nombre']}] Se reproducira solo el RUIDO 6 s. Enter...")
            ruido = np.zeros((int(6 * fs), 2), dtype=np.float32)
            ruido[:, 1] = estimulo[:len(ruido), 1] * 10 ** (c.get("ganancia_ruido_db", 0) / 20)
            reproducir(ruido)
        niveles[c["nombre"]] = pedir_nivel(f"Nivel PROMEDIO del ruido en '{c['nombre']}'")

    # 2. Orden de las tomas
    tomas_plan = [(c, r + 1) for c in cfg["condiciones"] for r in range(cfg["repeticiones"])]
    if cfg.get("orden_aleatorio"):
        random.Random(cfg.get("semilla_orden", 1)).shuffle(tomas_plan)

    print(f"\n=== MEDICION: {len(tomas_plan)} tomas. No hables ni muevas nada durante el experimento ===")
    grab = Grabador(cfg["puerto"])
    registro = {"carpeta": carpeta, "config": cfg, "estimulo": info, "nivel_voz_db": nivel_voz,
                "niveles_ruido_db": niveles, "tomas": []}
    esperado = int((PRE_GRAB + info["duracion_total_s"] + POST_GRAB) * FS_ESP32)
    condicion_actual = None
    try:
        for orden, (c, rep) in enumerate(tomas_plan, 1):
            if externo and c["nombre"] != condicion_actual:
                input(f"\nPon el ruido externo de '{c['nombre']}' ({niveles.get(c['nombre'])} dB). Enter...")
                time.sleep(2)
            condicion_actual = c["nombre"]
            senal = estimulo.copy()
            if not externo:
                senal[:, 1] *= 10 ** (c.get("ganancia_ruido_db", 0) / 20)

            grab.reiniciar_filtro()
            grab.iniciar()
            time.sleep(PRE_GRAB)
            reproducir(senal)
            time.sleep(POST_GRAB)
            audio = grab.detener()

            ok = len(audio) >= 0.97 * esperado
            audio = audio[:esperado]
            archivo = f"{orden:02d}_{c['nombre']}_rep{rep:02d}.wav"
            wavfile.write(os.path.join(carpeta, "tomas", archivo), FS_ESP32, audio)
            toma = {"orden": orden, "condicion": c["nombre"], "repeticion": rep, "archivo": archivo,
                    "fecha_hora": datetime.datetime.now().isoformat(timespec="seconds"), "muestras_ok": ok}
            registro["tomas"].append(toma)
            m = medir(audio, info) if len(audio) > 0 else {}
            aviso = "" if ok else "  <- AVISO: faltaron datos, repite esta toma"
            print(f"[{orden:2d}/{len(tomas_plan)}] {c['nombre']:<14} rep {rep}: "
                  f"SNR sin {m.get('snr_sin_db', float('nan')):5.1f} dB | "
                  f"con {m.get('snr_con_db', float('nan')):5.1f} dB | "
                  f"mejora {m.get('mejora_db', float('nan')):5.1f} dB{aviso}")
            time.sleep(1.0)
    finally:
        grab.cerrar()
        with open(os.path.join(carpeta, "registro.json"), "w", encoding="utf-8") as f:
            json.dump(registro, f, indent=2, ensure_ascii=False)

    analizar(carpeta)
    print(f"\nTodo guardado en: {carpeta}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--analizar":
        analizar(sys.argv[2])
    elif len(sys.argv) == 2:
        correr(sys.argv[1])
    else:
        print(__doc__)
