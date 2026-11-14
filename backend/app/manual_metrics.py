"""Supported manual readings and their fixed input units."""
GROUPS = [
    {"id": "blood_pressure", "label": "Blood pressure", "note": "Enter both pressures in mmHg.",
     "fields": [{"key": "systolic_bp", "label": "Systolic pressure", "unit": "mmHg"},
                {"key": "diastolic_bp", "label": "Diastolic pressure", "unit": "mmHg"}]},
    {"id": "glucose", "label": "Blood glucose", "note": "Enter mg/dL; no automatic unit conversion.",
     "fields": [{"key": "glucose", "label": "Blood glucose", "unit": "mg/dL"}]},
    {"id": "temperature", "label": "Body temperature", "note": "Enter degrees Celsius.",
     "fields": [{"key": "temperature_c", "label": "Body temperature", "unit": "°C"}]},
]
GROUP_BY_ID = {group["id"]: group for group in GROUPS}
LABELS = {field["key"]: field["label"] for group in GROUPS for field in group["fields"]}
