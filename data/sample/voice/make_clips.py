"""
Make SYNTHETIC voice test clips for POST /api/audio, with a "worsening" trend.

This is not a real voice: it is a buzz (like the vocal folds) passed through
three resonances (like the mouth), so it sounds like a robotic "aaa".
Counting is faked as short bursts with pauses. It is only meant to test
the pipeline and the dashboard.

Six recording sessions (day1 ... day6) of the same fake "astronaut". Each day
the voice gets a bit worse in two standard ways:
  - shimmer: the loudness wobbles more from one vocal-fold cycle to the next
  - wider formant bandwidths: the resonances are more damped, so the voice
    sounds duller / more muffled
We tuned these settings so the real voicebiomarker model gives a score that
goes up every day (roughly 0.7 -> 3.5). The score means "less like the
reference population", NOT edema, and it only goes up because we picked
settings that make it go up.

The clips are already in this folder (day1/ ... day6/, five WAV files each);
backend/tests/test_voice_audio.py uses them. To regenerate them, run from
the repository root with the backend's Python (numpy, scipy, soundfile):
    backend\\.venv\\Scripts\\python data\\sample\\voice\\make_clips.py
"""

from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import lfilter

SR = 16000          # samples per second
SEED = 2            # same seed every day = same fake person
HERE = Path(__file__).resolve().parent

# How bad each day is, from 0 (baseline) to 1 (worst).
DAYS = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]


def vowel(rng, seconds, f0=120.0, formants=(700, 1200, 2500), jitter=0.015,
          shimmer=0.0, bandwidth=80):
    """A held vowel: pulses at pitch f0, shaped by three formant filters."""
    src = np.zeros(int(seconds * SR))
    t = 0.0
    while t < seconds:
        i = int(t * SR)
        if i < src.size:
            src[i] = 1.0 * (1 + shimmer * rng.standard_normal())   # loudness wobble
        t += (1 / f0) * (1 + jitter * rng.standard_normal())       # pitch wobble
    y = src
    for f in formants:
        r = np.exp(-np.pi * bandwidth / SR)
        y = lfilter([1 - r], [1, -2 * r * np.cos(2 * np.pi * f / SR), r * r], y)
    return y / (np.max(np.abs(y)) + 1e-9) * 0.3


def counting(rng, seconds, fast=False, **voice):
    """Counting out loud, faked as short voiced bursts with pauses."""
    on, off = (0.25, 0.1) if fast else (0.4, 0.25)
    parts, total = [], 0.0
    while total < seconds:
        parts += [vowel(rng, on, f0=110 + 30 * rng.random(),
                        formants=(500 + 400 * rng.random(), 1500, 2500), **voice),
                  np.zeros(int(off * SR))]
        total += on + off
    return np.concatenate(parts)


def write(rng, path, y):
    y = (y + 1e-4 * rng.standard_normal(y.size)).astype(np.float32)   # tiny room noise
    sf.write(path, y, SR, subtype="PCM_16")


def make_day(folder: Path, severity: float):
    rng = np.random.default_rng(SEED)
    voice = {"shimmer": 0.25 * severity, "bandwidth": 80 + 200 * severity}
    folder.mkdir(exist_ok=True)
    write(rng, folder / "counting_normal.wav", counting(rng, 14, **voice))
    write(rng, folder / "counting_fast.wav", counting(rng, 10, fast=True, **voice))
    write(rng, folder / "vowel_a.wav", vowel(rng, 6, formants=(750, 1200, 2500), **voice))
    write(rng, folder / "vowel_e.wav", vowel(rng, 6, formants=(450, 2000, 2700), **voice))
    write(rng, folder / "vowel_o.wav", vowel(rng, 6, formants=(500, 900, 2400), **voice))


if __name__ == "__main__":
    for n, severity in enumerate(DAYS, start=1):
        make_day(HERE / f"day{n}", severity)
        print(f"day{n}: severity {severity}")
