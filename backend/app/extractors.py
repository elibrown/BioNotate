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


EXTRACTORS = {
    "cardioresp": _cardioresp,
}


def extract_measurements(result: dict) -> list[dict]:
    extractor = EXTRACTORS.get(str(result.get("model")))
    return extractor(result) if extractor else []
