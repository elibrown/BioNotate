"""Provisional intake catalogue, not a clinical standard or alert policy.

BM codes were supplied by the team. Confirm analytes, units and protocols
with the device/lab owner before connecting automated feeds.
"""


def field(key, label, unit):
    return {"key": key, "label": label, "unit": unit}


def group(code, label, fields, note=""):
    return {"id": code, "label": label, "fields": fields, "note": note}


GROUPS = [
    group("VITALS", "Temperature", [field("temperature_c", "Body temperature", "°C")],
          "Record Celsius. Measurement site and device need a future metadata field."),
    group("BM01_CBC_WBC_Lymph_Hgb", "CBC / blood counts", [
        field("wbc", "White blood cells", "10^9/L"),
        field("lymphocytes_absolute", "Lymphocytes (absolute)", "10^9/L"),
        field("lymphocytes_percent", "Lymphocytes", "%"),
        field("hemoglobin", "Hemoglobin", "g/dL")]),
    group("BM02_CMP_Glucose_Ca_Renal", "Metabolic / renal panel", [
        field("glucose", "Glucose", "mg/dL"), field("calcium", "Calcium", "mg/dL"),
        field("creatinine", "Creatinine", "mg/dL"), field("bun", "Blood urea nitrogen", "mg/dL")],
          "Selected CMP/renal fields, not a complete CMP. Copy only results in the displayed units."),
    group("BM03_Blood_CRP_Cytokines", "Inflammation", [field("crp", "C-reactive protein", "mg/L")],
          "Cytokines require named analytes, assay identifiers and assay-specific units; not accepted yet."),
    group("BM04_Urine_Ca_USG_pH_Citrate", "Urine chemistry", [
        field("urine_calcium_spot", "Urine calcium (spot concentration)", "mg/dL"),
        field("urine_specific_gravity", "Urine specific gravity", "1"),
        field("urine_ph", "Urine pH", "pH"),
        field("urine_citrate_24h", "Urine citrate (24-hour collection)", "mg/24h")],
          "Spot concentrations and 24-hour excretion are different measurements. Do not interchange them."),
    group("BM05_Urine_Proteomics_UTI", "Urine proteomics / UTI", [],
          "Requires protein/analyte identifiers, assay units, culture/organism findings and report files. Format pending; not a single number."),
    group("BM06_HR_HRV_RMSSD", "Heart rate / variability", [
        field("hr_bpm", "Heart rate", "bpm"), field("rmssd", "RMSSD", "ms")],
          "Record the device's RMSSD; recording window and artefact handling must be agreed for comparisons."),
    group("BM07_Respiratory_Rate_CO2", "Respiration / CO₂", [
        field("respiratory_rate", "Respiratory rate", "breaths/min"),
        field("end_tidal_co2", "End-tidal CO₂", "mmHg")],
          "End-tidal CO₂ is one proposed CO₂ measure; blood CO₂ and cabin CO₂ require different keys/units."),
    group("BM08_PTT_Blood_Pressure", "Blood pressure / pulse transit time", [
        field("systolic_bp", "Systolic pressure", "mmHg"),
        field("diastolic_bp", "Diastolic pressure", "mmHg"),
        field("ptt", "Pulse transit time", "ms")],
          "Enter systolic and diastolic together. PTT is not a pressure reading or a direct substitute for cuff BP."),
    group("BM09_Sleep_WASO_Efficiency", "Sleep", [
        field("waso", "Wake after sleep onset", "min"),
        field("sleep_efficiency", "Sleep efficiency", "%")],
          "The sleep period and device definition must be included in a future session contract."),
    group("BM10_ONSD_IJV_Ultrasound", "Ultrasound", [
        field("onsd_left", "Optic nerve sheath diameter (left)", "mm"),
        field("onsd_right", "Optic nerve sheath diameter (right)", "mm")],
          "Numeric ONSD summaries only. IJV flow, posture/site metadata and ultrasound images need a separate contract."),
    group("BM11_Cognitive_PERCLOS_CTB", "Cognition / eye closure", [
        field("perclos", "PERCLOS", "%")],
          "Specify eye-closure definition and observation window in the future contract. CTB meaning/test battery is unconfirmed."),
    group("BM12_Skin_Rash_Microbiome", "Skin / microbiome", [],
          "Requires rash observations/images and microbiome taxa/abundances or sequencing files. Format pending; no invented severity scale."),
]

GROUP_BY_ID = {item["id"]: item for item in GROUPS}
FIELD_BY_KEY = {item["key"]: {**item, "group_id": panel["id"]}
                for panel in GROUPS for item in panel["fields"]}
