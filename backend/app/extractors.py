"""
Turn a model's output into measurements (rows for the `measurements` table).

Each model returns its own JSON shape. For each model we write one small
function that picks out the numbers we want to keep and says which
biomarker they belong to. Register it in EXTRACTORS under the model's name
(the "model" field of its output).

Add a new model = add one function + one line in EXTRACTORS.
A model with no extractor still gets its prediction saved, just no
measurements.
"""


def _rppg(result: dict) -> list[dict]:
    """
    rPPG heart-rate model. Example output:
        {"model": "rppg", "status": "ok", "hr_bpm": 62.2,
         "measurements": [{"timestamp_s": 30.01, "hr_bpm": 62.6}, ...]}

    We keep the overall hr_bpm (one value per video). The per-second series
    stays available in the prediction's full result.
    """
    hr = result.get("hr_bpm")
    if hr is None:
        return []
    return [{"biomarker": "BM06_HR_HRV_RMSSD", "metric": "hr_bpm", "value": hr, "unit": "bpm"}]


EXTRACTORS = {
    "rppg": _rppg,
}


def extract_measurements(result: dict) -> list[dict]:
    extractor = EXTRACTORS.get(str(result.get("model")))
    return extractor(result) if extractor else []
