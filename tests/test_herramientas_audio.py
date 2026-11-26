import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import grabar_audio
from analizar_snr import snr
from evaluar_prueba import estimar_latencia, leer_metricas_firmware
from experimento.experimento import extraer_bloques as extraer_bloques_experimento


def crear_trama(secuencia, muestras):
    return (
        b"\xAA\x55"
        + struct.pack("<HI", len(muestras), secuencia)
        + muestras.astype("<i2").tobytes()
    )


def guardar_wav(ruta, muestras, frecuencia):
    with wave.open(str(ruta), "wb") as archivo:
        archivo.setnchannels(1)
        archivo.setsampwidth(2)
        archivo.setframerate(frecuencia)
        archivo.writeframes(muestras.astype("<i2").tobytes())


class PruebasProtocoloAudio(unittest.TestCase):
    def test_decodifica_tramas_fragmentadas_en_ambos_receptores(self):
        muestras = np.array([[10, -10], [200, -200]], dtype=np.int16)
        datos = b"ruido" + crear_trama(17, muestras) + crear_trama(18, muestras)

        for decodificar in (
            grabar_audio.extraer_bloques,
            extraer_bloques_experimento,
        ):
            with self.subTest(decodificador=decodificar.__module__):
                primeros, resto = decodificar(datos[:9])
                self.assertEqual(primeros, [])
                tramas, resto = decodificar(resto + datos[9:])
                self.assertEqual([secuencia for secuencia, _ in tramas], [17, 18])
                np.testing.assert_array_equal(tramas[0][1], muestras)
                self.assertEqual(resto, b"")


class PruebasMetricas(unittest.TestCase):
    def test_snr_no_inventa_valor_en_silencio_digital(self):
        estimacion, potencia_ruido = snr(np.zeros(16000), 16000)
        self.assertIsNone(estimacion)
        self.assertEqual(potencia_ruido, 0)

    def test_estima_retraso_conocido(self):
        rng = np.random.default_rng(42)
        referencia = rng.normal(0, 3000, 16000).astype(np.int16)
        retraso = 96
        bluetooth = np.concatenate(
            (np.zeros(retraso, dtype=np.int16), referencia[:-retraso])
        )

        with tempfile.TemporaryDirectory() as directorio:
            referencia_wav = Path(directorio) / "referencia.wav"
            bluetooth_wav = Path(directorio) / "bluetooth.wav"
            guardar_wav(referencia_wav, referencia, 8000)
            guardar_wav(bluetooth_wav, bluetooth, 8000)

            resultado = estimar_latencia(referencia_wav, bluetooth_wav, 2)

        self.assertEqual(resultado["retardo_bt_muestras"], retraso)
        self.assertTrue(resultado["latencia_confiable"])

    def test_extrae_diferencias_de_contadores_del_firmware(self):
        linea = (
            "I METRICAS conectado=1 fs_bt=16000 i2s_muestras={muestras} "
            "i2s_errores={errores} clip_m1=0 clip_m2=0 clip_salida=0 "
            "muestras_salida=20 cola_perdida_bytes={perdida} "
            "hfp_solicitado_bytes=30 hfp_silencio_bytes={silencio} "
            "hfp_audio_conexiones=1 hfp_audio_desconexiones=0\n"
        )
        with tempfile.TemporaryDirectory() as directorio:
            log = Path(directorio) / "firmware.log"
            log.write_text(
                linea.format(muestras=100, errores=0, perdida=1, silencio=2)
                + linea.format(muestras=200, errores=1, perdida=5, silencio=8),
                encoding="utf-8",
            )

            resultado = leer_metricas_firmware(log)

        self.assertEqual(resultado["i2s_errores_en_prueba"], 1)
        self.assertEqual(resultado["cola_perdida_bytes_en_prueba"], 4)
        self.assertEqual(resultado["hfp_silencio_bytes_en_prueba"], 6)


if __name__ == "__main__":
    unittest.main()
