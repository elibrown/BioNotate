"""
Voice model adapter for AstroHealth (voicebiomarker 0.1.0).

The astronaut records FIVE short clips (TASKS below). The model returns a
"vocal biomarker" score plus voice-quality measures (pitch, voice clarity,
jitter, shimmer, ...).

READ BEFORE SHOWING THE NUMBER: the model was trained on public data with a
stand-in label (self-reported heart disease, hypertension or diabetes), NOT
on edema. Its README says the score is research data with no clinical
cutoff. See the README in the voicebiomarker handoff.

Errors (raised, the upload route turns them into HTTP errors):
  UndecodableAudio  a clip isn't readable audio           -> 400
  RecordingTooLong  all clips together are over 120 s     -> 413
A bad recording (too noisy, too short, ...) is NOT an error: the result has
status "rejected" and a "reason", and is saved like any other result.
"""

from pathlib import Path

from voicebiomarker import analyze_clips
from voicebiomarker.api import RecordingTooLong
from voicebiomarker.audio import UndecodableAudio
from voicebiomarker.config import MAX_UPLOAD_BYTES, TASKS

MODEL_NAME = "voicebiomarker"

# What the astronaut is asked to do for each clip (the upload field names).
TASK_INSTRUCTIONS = {
    "counting_normal": "Count from 1 to 20 at a normal pace (about 10 s).",
    "counting_fast": "Count from 1 to 20 fast (about 6 s).",
    "vowel_a": 'Hold "aaa" at a comfortable pitch for at least 5 s.',
    "vowel_e": 'Hold "eee" for at least 5 s.',
    "vowel_o": 'Hold "ooo" for at least 5 s.',
}

# What to tell the astronaut when a recording is rejected (from the model README).
REJECTION_ADVICE = {
    "clipping": "Move the microphone further away or lower the input volume.",
    "low_snr": "Find a quieter place.",
    "vowel_too_short": "Hold each vowel for 5 seconds.",
    "too_little_speech": "Count all the way to 20 and hold the vowels longer.",
}

__all__ = [
    "MODEL_NAME", "TASKS", "TASK_INSTRUCTIONS", "MAX_UPLOAD_BYTES",
    "RecordingTooLong", "UndecodableAudio", "run_model",
]


def run_model(clips: dict[str, Path]) -> dict:
    """
    Analyse one recording: `clips` maps each task name in TASKS to a file.
    Returns JSON-serializable results. CPU-heavy (several seconds).
    """
    reading = analyze_clips({task: str(path) for task, path in clips.items()})
    result = {"model": MODEL_NAME, **reading.to_dict()}
    if reading.reason:
        result["advice"] = REJECTION_ADVICE.get(reading.reason)
    return result
