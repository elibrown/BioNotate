"""Supported manual metrics and fixed input units."""
METRICS = [
    {"key": "systolic_bp", "label": "Systolic blood pressure", "unit": "mmHg"},
    {"key": "diastolic_bp", "label": "Diastolic blood pressure", "unit": "mmHg"},
    {"key": "glucose", "label": "Blood glucose", "unit": "mg/dL"},
    {"key": "temperature_c", "label": "Body temperature", "unit": "°C"},
]
METRIC_BY_KEY = {metric["key"]: metric for metric in METRICS}
LABELS = {metric["key"]: metric["label"] for metric in METRICS}
