#pragma once
#include <math.h>
#include <stdbool.h>
#include <string.h>

// ---------------- Ajustes ----------------
#define FR_FS            16000.0f // frecuencia de muestreo (Hz)
#define FR_CORTE_BAJO      300.0f // Hz: elimina zumbidos graves
#define FR_CORTE_ALTO     3400.0f // Hz: elimina siseos agudos
#define FR_TAPS             128   // longitud del filtro adaptativo (8 ms)
#define FR_RETARDO           16   // retardo del mic 1 (1 ms)
#define FR_MU              0.10f  // velocidad de aprendizaje NLMS
#define FR_RELACION_VOZ     2.5f  // energia mic1/mic2 para considerar que hay voz
#define FR_GANANCIA_GATE   0.05f  // nivel en silencios (-26 dB antes de ganancia final)
#define FR_GANANCIA         0.5f  // amplificacion final
#define FR_CALIBRACION_MS   400   // calibracion inicial sin asumir que hay voz
#define FR_ON_MS             64   // persistencia minima para abrir la compuerta
#define FR_OFF_MS           160   // retencion para no cortar entre silabas
#define FR_MAX_BLOQUE       512
#define FR_PI       3.14159265f

typedef struct { float b0, b1, b2, a1, a2, z1, z2; } fr_biquad_t;

typedef struct {
  bool dos_mics;
  fr_biquad_t hp1, lp1, hp2, lp2;
  float dc_x, dc_y;
  float w[FR_TAPS];
  float xb[2 * FR_TAPS];
  int pos;
  float pot_ref;
  float retardo[FR_RETARDO];
  int pos_ret;
  float piso;
  bool primer_bloque;
  float g;
  bool voz;
  float rms1, rms2, relacion;
  int muestras_calibracion;
  int muestras_on, muestras_off;
  float t1[FR_MAX_BLOQUE], t2[FR_MAX_BLOQUE];
} fr_estado_t;

static inline float fr_limitar(float x) { return x > 1.0f ? 1.0f : (x < -1.0f ? -1.0f : x); }

// tipo 0 = pasa-altos, 1 = pasa-bajos (Butterworth de 2.o orden)
static inline void fr_biquad_iniciar(fr_biquad_t *f, int tipo, float fc, float fs) {
  float w0 = 2.0f * FR_PI * fc / fs, c = cosf(w0), alfa = sinf(w0) / (2.0f * 0.7071f);
  float a0 = 1.0f + alfa;
  if (tipo == 0) { f->b0 = (1.0f + c) / 2.0f; f->b1 = -(1.0f + c); f->b2 = (1.0f + c) / 2.0f; }
  else           { f->b0 = (1.0f - c) / 2.0f; f->b1 = 1.0f - c;    f->b2 = (1.0f - c) / 2.0f; }
  f->a1 = -2.0f * c; f->a2 = 1.0f - alfa;
  f->b0 /= a0; f->b1 /= a0; f->b2 /= a0; f->a1 /= a0; f->a2 /= a0;
  f->z1 = f->z2 = 0.0f;
}

static inline float fr_biquad(fr_biquad_t *f, float x) {
  float y = f->b0 * x + f->z1;
  f->z1 = f->b1 * x - f->a1 * y + f->z2;
  f->z2 = f->b2 * x - f->a2 * y;
  return y;
}

static inline void fr_iniciar(fr_estado_t *s, bool dos_mics) {
  memset(s, 0, sizeof(*s));
  s->dos_mics = dos_mics;
  fr_biquad_iniciar(&s->hp1, 0, FR_CORTE_BAJO, FR_FS);
  fr_biquad_iniciar(&s->lp1, 1, FR_CORTE_ALTO, FR_FS);
  fr_biquad_iniciar(&s->hp2, 0, FR_CORTE_BAJO, FR_FS);
  fr_biquad_iniciar(&s->lp2, 1, FR_CORTE_ALTO, FR_FS);
  s->primer_bloque = true;
  s->muestras_calibracion = (int)(FR_FS * FR_CALIBRACION_MS / 1000.0f);
  s->g = 1.0f;
}

// m1: mic 1 (voz), m2: mic 2 (ruido, NULL si hay 1 solo mic)
// filtrada: salida con reduccion de ruido, original: mic 1 sin filtrar
static inline void fr_procesar(fr_estado_t *s, const float *m1, const float *m2,
                               float *filtrada, float *original, int n) {
  if (!s || !m1 || n <= 0) return;
  if (n > FR_MAX_BLOQUE) n = FR_MAX_BLOQUE;
  bool dos = s->dos_mics && m2 != NULL;

  // 1. Pasa-banda de voz y energia de cada microfono
  float e1 = 0.0f, e2 = 0.0f;
  for (int i = 0; i < n; i++) {
    float y = m1[i] - s->dc_x + 0.995f * s->dc_y;
    s->dc_x = m1[i]; s->dc_y = y;
    if (original) original[i] = fr_limitar(y * FR_GANANCIA);

    float a = fr_biquad(&s->lp1, fr_biquad(&s->hp1, m1[i]));
    s->t1[i] = a; e1 += a * a;
    if (dos) {
      float b = fr_biquad(&s->lp2, fr_biquad(&s->hp2, m2[i]));
      s->t2[i] = b; e2 += b * b;
    }
  }
  float rms1 = sqrtf(e1 / n);
  float rms2 = dos ? sqrtf(e2 / n) : 0.0f;
  s->rms1 = rms1;
  s->rms2 = rms2;
  s->relacion = e2 > 1e-14f ? e1 / e2 : (e1 > 1e-14f ? 1e6f : 0.0f);

  // 2. Detector de voz con calibracion, histéresis y retencion de estado
  if (s->primer_bloque) {
    s->piso = rms1;
    s->primer_bloque = false;
  }

  if (s->muestras_calibracion > 0) {
    s->piso = 0.9f * s->piso + 0.1f * rms1;
    s->muestras_calibracion -= n;
    if (s->muestras_calibracion < 0) s->muestras_calibracion = 0;
  }

  bool cumple_on = false;
  bool cumple_off = false;
  if (dos) {
    cumple_on = rms1 > 1.8f * s->piso &&
                s->relacion >= FR_RELACION_VOZ;
    cumple_off = rms1 > 1.35f * s->piso &&
                 s->relacion >= (FR_RELACION_VOZ * 0.75f);
  } else {
    cumple_on = rms1 > 3.0f * s->piso;
    cumple_off = rms1 > 2.0f * s->piso;
  }

  int umbral_on = (int)(FR_FS * FR_ON_MS / 1000.0f);
  int umbral_off = (int)(FR_FS * FR_OFF_MS / 1000.0f);
  if (s->muestras_calibracion <= 0) {
    if (!s->voz) {
      s->muestras_on = cumple_on ? s->muestras_on + n : 0;
      s->muestras_off = 0;
      if (s->muestras_on >= umbral_on) {
        s->voz = true;
        s->muestras_on = 0;
      }
    } else {
      s->muestras_off = cumple_off ? 0 : s->muestras_off + n;
      s->muestras_on = 0;
      if (s->muestras_off >= umbral_off) {
        s->voz = false;
        s->muestras_off = 0;
      }
    }
  } else {
    s->muestras_on = 0;
    s->muestras_off = 0;
  }

  // Solo el silencio valida y actualiza el piso de ruido.
  if (!s->voz && !cumple_on) s->piso = 0.92f * s->piso + 0.08f * rms1;
  float objetivo = s->voz ? 1.0f : FR_GANANCIA_GATE;

  for (int i = 0; i < n; i++) {
    float salida = s->t1[i];

    // 3. Cancelacion adaptativa (NLMS): estima el ruido con el mic 2 y lo resta
    if (dos) {
      float d = s->retardo[s->pos_ret];
      s->retardo[s->pos_ret] = s->t1[i];
      s->pos_ret = (s->pos_ret + 1) % FR_RETARDO;

      float x = s->t2[i];
      s->pos = (s->pos == 0) ? FR_TAPS - 1 : s->pos - 1;
      s->xb[s->pos] = x;
      s->xb[s->pos + FR_TAPS] = x;
      const float *v = &s->xb[s->pos];
      s->pot_ref = 0.995f * s->pot_ref + 0.005f * x * x;

      float estimado = 0.0f;
      for (int k = 0; k < FR_TAPS; k++) estimado += s->w[k] * v[k];
      float err = d - estimado;

      if (!s->voz && !cumple_on) {   // no aprende sobre voz ni sus ataques
        float paso = FR_MU * err / (FR_TAPS * s->pot_ref + 1e-10f);
        for (int k = 0; k < FR_TAPS; k++) s->w[k] += paso * v[k];
      }
      salida = err;
    }

    // 4. Compuerta de ruido con transicion suave
    float suavizado = objetivo > s->g ? 0.01f : 0.002f;
    s->g += suavizado * (objetivo - s->g);
    if (filtrada) filtrada[i] = fr_limitar(salida * s->g * FR_GANANCIA);
  }
}
