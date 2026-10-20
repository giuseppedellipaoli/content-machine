"""Genera sound FX sintetici (numpy → wav 48k stereo) per gli shorts.

Suoni: whoosh (entrata card), wipeout (uscita), tickroll (contatore),
pop (voce lista / obiezione), thud (timbro). Zero sample esterni, zero licenze.
"""
from __future__ import annotations

import _bootstrap  # shared local paths, tools and cache

import wave
from pathlib import Path

import numpy as np

SR = 48000
OUT = Path(__file__).parent / "sfx"
OUT.mkdir(exist_ok=True)

rng = np.random.default_rng(7)


def save(name: str, x: np.ndarray, gain: float = 0.9) -> None:
    x = x / (np.max(np.abs(x)) + 1e-9) * gain
    pcm = (x * 32767).astype(np.int16)
    stereo = np.column_stack([pcm, pcm]).ravel()
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
    print(f"OK sfx/{name}.wav ({len(x)/SR:.2f}s)")


def env(n: int, attack: float, decay: float) -> np.ndarray:
    a = int(n * attack)
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a)
    e[a:] = np.exp(-np.linspace(0, decay, n - a))
    return e


def lowpass(x: np.ndarray, alpha: float) -> np.ndarray:
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += alpha * (v - acc)
        y[i] = acc
    return y


# whoosh: noise con bandpass che sale, breve
n = int(0.28 * SR)
noise = rng.standard_normal(n)
sweep = lowpass(noise, 0.12) - lowpass(noise, 0.03)
save("whoosh", sweep * env(n, 0.35, 5.5), 0.7)

# wipeout: whoosh inverso, più corto e scuro
n = int(0.22 * SR)
noise = rng.standard_normal(n)
save("wipeout", (lowpass(noise, 0.06) - lowpass(noise, 0.02)) * env(n, 0.15, 6.0), 0.6)

# tickroll: 18 tick accelerati in 2.4s (per il contatore)
n = int(2.6 * SR)
x = np.zeros(n)
t = 0.0
dt = 0.24
for _ in range(18):
    i = int(t * SR)
    tick_n = int(0.012 * SR)
    if i + tick_n < n:
        tick = rng.standard_normal(tick_n) * env(tick_n, 0.05, 9.0)
        x[i : i + tick_n] += lowpass(tick, 0.5)
    t += dt
    dt = max(0.055, dt * 0.82)
# ding finale al termine della corsa
i = int(t * SR)
m = int(0.5 * SR)
if i + m < n:
    tt = np.arange(m) / SR
    x[i : i + m] += 0.5 * np.sin(2 * np.pi * 1318.5 * tt) * np.exp(-tt * 7)
save("tickroll", x, 0.55)

# pop: sine burst con pitch drop
n = int(0.09 * SR)
tt = np.arange(n) / SR
freq = 620 * np.exp(-tt * 18) + 180
save("pop", np.sin(2 * np.pi * np.cumsum(freq) / SR) * env(n, 0.08, 7.0), 0.65)

# thud: colpo del timbro — noise burst scuro + sub
n = int(0.34 * SR)
tt = np.arange(n) / SR
noise = lowpass(rng.standard_normal(n), 0.045)
sub = np.sin(2 * np.pi * (95 * np.exp(-tt * 9) + 42) * tt)
save("thud", (noise * 0.7 + sub * 0.8) * env(n, 0.02, 8.0), 0.95)

print("Tutti gli SFX generati.")
