"""
Turn a model's output into measurements (rows for the `measurements` table).

Each model returns its own JSON shape and has its own metrics. For each model
we write one small function that picks out every reading we want to keep, as
{metric, value, unit, offset_s}. The model's name is saved as the source.
Register the function in EXTRACTORS under the model's name (the "model"
field of its output).

Add a new model = add one function + one line in EXTRACTORS.
A model with no extractor still gets its prediction saved, just no
measurements.
"""

# Reading statuses from cardioresp that carry usable values.
# ("warming_up" and "no_face" readings have none, so they're skipped.)
CARDIORESP_GOOD_STATUSES = {"ok", "partial"}


def _cardioresp(result: dict) -> list[dict]:
    """
    cardioresp model (HR, respiratory rate, PRQ). Example output:
        {"model": "cardioresp", "status": "ok", ...,
         "measurements": [
             {"timestamp_s": 30.0, "hr_bpm": 71.8, "respi_rate": 13.9,
              "prq": 5.17, "status": "ok", "log_message": ""},
             ...]}

    We keep EVERY usable reading: one row per metric per reading, so a 60 s
    video gives about 30 readings x 3 metrics. A "partial" reading has HR
    but no RR/PRQ, so only its HR is kept. A respiratory rate of 0 or less
    is not a real reading and is skipped.
    """
    wanted = [
        ("hr_bpm", "bpm"),
        ("respi_rate", "breaths/min"),
        ("prq", None),          # PRQ = HR / RR, no unit
    ]
    rows = []
    for reading in result.get("measurements") or []:
        if reading.get("status") not in CARDIORESP_GOOD_STATUSES:
            continue
        for metric, unit in wanted:
            value = reading.get(metric)
            if value is None:
                continue
            if metric in ("respi_rate", "prq") and value <= 0:
                continue
            rows.append({
                "metric": metric,
                "value": value,
                "unit": unit,
                "offset_s": reading.get("timestamp_s"),
            })
    return rows


# voicebiomarker voice_quality fields we keep, with their units.
VOICE_QUALITY_UNITS = {
    "f0_median_hz": "Hz",    # median pitch
    "f0_sd_hz": "Hz",        # pitch steadiness
    "cpp_db": "dB",          # voice clarity (higher is clearer)
    "cpp_sd_db": "dB",       # variation of voice clarity
    "jitter_pct": "%",       # cycle-to-cycle pitch irregularity
    "shimmer_pct": "%",      # cycle-to-cycle loudness irregularity
    "hnr_db": "dB",          # harmonics-to-noise ratio
    "creak_pct": "%",        # share of creaky voice (approximate)
}


def _voicebiomarker(result: dict) -> list[dict]:
    """
    voicebiomarker model (five voice clips). Example output:
        {"model": "voicebiomarker", "status": "ok", "reason": null,
         "vocal_biomarker": 0.23, "quartile": 3,
         "voice_quality": {"f0_median_hz": 208.9, "cpp_db": 15.11, ...},
         "net_speech_s": 31.4, "windows_used": 2,
         "model_version": "coswara-cm-0.1.0"}

    One value per recording, so one row per metric and no offset_s.
    A "rejected" recording has no values, so it gives no rows.
    Any voice_quality value can be null; those are skipped.
    """
    if result.get("status") != "ok":
        return []
    rows = []
    if result.get("vocal_biomarker") is not None:
        rows.append({"metric": "vocal_biomarker", "value": result["vocal_biomarker"],
                     "unit": "z-score"})
    for metric, value in (result.get("voice_quality") or {}).items():
        if value is not None and metric in VOICE_QUALITY_UNITS:
            rows.append({"metric": metric, "value": value,
                         "unit": VOICE_QUALITY_UNITS[metric]})
    return rows


EXTRACTORS = {
    "cardioresp": _cardioresp,
    "voicebiomarker": _voicebiomarker,
}


def extract_measurements(result: dict) -> list[dict]:
    extractor = EXTRACTORS.get(str(result.get("model")))
    return extractor(result) if extractor else []
