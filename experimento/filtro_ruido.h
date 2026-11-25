/*
  filtro_ruido.h - Reduccion de ruido para 1 o 2 microfonos
  Sistema de Captura de Voz Inalambrica con Mitigacion de Ruido (ESP32)

  Etapas:
    1. Pasa-banda de voz (300-3400 Hz)
    2. Detector de voz (compara la energia del mic 1 con la del mic 2)
    3. Cancelacion adaptativa de ruido NLMS (solo con 2 microfonos)
    4. Compuerta de ruido (baja el volumen en los silencios)

  Las muestras entran y salen como float entre -1.0 y 1.0, a 16 kHz.
*/
#pragma once
#include <math.h>
#include <stdbool.h>
#include <string.h>

// ---------------- Ajustes ----------------
#define FR_FS            16000.0f // frecuencia de muestreo (Hz)
#define FR_CORTE_BAJO      300.0f // Hz: elimina zumbidos graves
#define FR_CORTE_ALTO     3400.0f // Hz: elimina siseos agudos
#define FR_TAPS              64   // longitud del filtro adaptativo (4 ms)
#define FR_RETARDO           16   // retardo del mic 1 para el filtro adaptativo (1 ms)
#define FR_MU              0.05f  // velocidad de aprendizaje del filtro adaptativo
#define FR_RELACION_VOZ     2.0f  // energia mic1 / mic2 para considerar que hay voz
#define FR_GANANCIA_GATE   0.25f  // volumen en silencios (0.25 = -12 dB)
#define FR_GANANCIA         8.0f  // amplificacion final
#define FR_MAX_BLOQUE       512   // muestras maximas por bloque
#define FR_PI       3.14159265f

typedef struct { float b0, b1, b2, a1, a2, z1, z2; } fr_biquad_t;

typedef struct {
  bool dos_mics;
  fr_biquad_t hp1, lp1, hp2, lp2;   // pasa-banda de cada microfono
  float dc_x, dc_y;                 // quita el nivel DC de la senal original
  float w[FR_TAPS];                 // coeficientes del filtro adaptativo
  float xb[2 * FR_TAPS];            // historial del mic 2 (referencia de ruido)
  int pos;
  float pot_ref;                    // potencia de la referencia
  float retardo[FR_RETARDO];
  int pos_ret;
  float piso;                       // nivel de ruido estimado (RMS)
  bool primer_bloque;
  float g;                          // ganancia actual de la compuerta
  bool voz;                         // true si el ultimo bloque tenia voz
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
  s->g = 1.0f;
}

/*
  m1: microfono 1 (voz)   m2: microfono 2 (ruido, puede ser NULL con 1 microfono)
  filtrada: salida con reduccion de ruido   original: mic 1 sin filtrar (para comparar)
  n: numero de muestras (maximo FR_MAX_BLOQUE)
*/
static inline void fr_procesar(fr_estado_t *s, const float *m1, const float *m2,
                               float *filtrada, float *original, int n) {
  if (n > FR_MAX_BLOQUE) n = FR_MAX_BLOQUE;
  bool dos = s->dos_mics && m2 != NULL;

  // 1. Pasa-banda de voz y energia de cada microfono
  float e1 = 0.0f, e2 = 0.0f;
  for (int i = 0; i < n; i++) {
    float y = m1[i] - s->dc_x + 0.995f * s->dc_y;      // original sin DC
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

  // 2. Detector de voz
  if (s->primer_bloque) { s->piso = rms1; s->primer_bloque = false; }
  bool voz = dos ? (rms1 > 2.0f * s->piso && e1 > FR_RELACION_VOZ * e2)
                 : (rms1 > 3.0f * s->piso);
  if (!voz) s->piso = 0.9f * s->piso + 0.1f * rms1;   // aprende el nivel de ruido
  else      s->piso *= 1.005f;                         // evita quedarse "pegado"
  s->voz = voz;
  float objetivo = voz ? 1.0f : FR_GANANCIA_GATE;

  for (int i = 0; i < n; i++) {
    float salida = s->t1[i];

    // 3. Cancelacion adaptativa: estima el ruido del mic 1 a partir del mic 2 y lo resta
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

      if (!voz) {   // solo aprende cuando no hablas, para no borrar tu voz
        float paso = FR_MU * err / (FR_TAPS * s->pot_ref + 1e-10f);
        for (int k = 0; k < FR_TAPS; k++) s->w[k] += paso * v[k];
      }
      salida = err;
    }

    // 4. Compuerta de ruido con transicion suave
    s->g += 0.002f * (objetivo - s->g);
    if (filtrada) filtrada[i] = fr_limitar(salida * s->g * FR_GANANCIA);
  }
}
