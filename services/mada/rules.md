# step3_clinical_knowledge_and_tree.py
# Plain-English astronaut guide, physiological valid bounds, thresholds,
# preventive care (from NASA HRP research), and ISS Medical Checklist (JSC-48522) protocols.

# Clean ASCII/Matplotlib-safe Emergency Action Protocols from ISS Medical Checklist (JSC-48522)
ISS_EMERGENCY_PROTOCOLS = {
    "ANAPHYLAXIS": {
        "title": "[EMERGENCY] ANAPHYLAXIS (Severe Allergic Reaction) - ISS Checklist JSC-48522",
        "steps": [
            "1. AIRWAY & RESTRAINT: Remove trigger. Strap astronaut flat on Crew Medical Restraint System (CMRS).",
            "2. EPINEPHRINE (IMMEDIATE): Inject Epinephrine 0.3 mg (1:1000) IM into outer mid-thigh.",
            "3. 100% OXYGEN: Apply Non-Rebreather Mask at 10-15 L/min.",
            "4. INHALER & MEDS: Give Albuterol (2-4 puffs) for wheezing + Diphenhydramine 25-50 mg IM/PO + Methylprednisolone 125 mg.",
            "5. 5-MIN RECHECK: Repeat Epinephrine 0.3 mg IM every 5-15 min (up to 3 doses) if breathing/BP does not improve."
        ]
    },
    "PSYCHOSIS": {
        "title": "[EMERGENCY] ACUTE PSYCHOSIS / BEHAVIORAL CRISIS - ISS Checklist JSC-48522",
        "steps": [
            "1. CABIN SAFETY: Lock away medical sharps, tools, and secure critical hatch/life-support switches.",
            "2. DE-ESCALATE: Speak in a slow, calm voice. Do not argue with delusions.",
            "3. CHECK MEDICAL TRIGGERS: Check Blood Sugar, Cabin CO2 / RR, and extreme Sleep Loss.",
            "4. SAFE RESTRAINT (LAST RESORT): If danger to self/crew/ship, use CMRS soft straps with 2-3 crew members.",
            "5. MEDICATION (With Flight Surgeon): Administer Haloperidol 5 mg IM + Lorazepam 2 mg IM/PO; keep 1-on-1 watch."
        ]
    },
    "CHEST_PAIN": {
        "title": "[EMERGENCY] ACUTE CHEST PAIN (Cardiac / Thoracic) - ISS Checklist JSC-48522",
        "steps": [
            "1. STOP EXERTION: Halt work/exercise immediately and secure comfortably on CMRS board. Have the attending medical officer arrive and continue treatment.",
            "2. VITALS & O2: Check HR, RR, and BP (#8). Start 100% O2 if SpO2 < 94%.",
            "3. CHEW ASPIRIN: Give Aspirin 325 mg PO (chewed before swallowing).",
            "4. 12-LEAD ECG & AED: Record 12-lead ECG for Mission Control and place AED right next to patient.",
            "5. NITROGLYCERIN: If Systolic BP > 100 mmHg, give Nitroglycerin 0.4 mg under tongue every 5 min (max 3 doses)."
        ]
    },
    "CHOKING": {
        "title": "[EMERGENCY] CHOKING IN ZERO GRAVITY (Blocked Airway) - ISS Checklist JSC-48522",
        "steps": [
            "1. ASSESS COUGH: If astronaut can cough forcefully or speak, encourage coughing.",
            "2. BRACE IN ZERO-G: Anchor your feet in foot loops or brace your back against a bulkhead wall.",
            "3. ABDOMINAL THRUSTS: Wrap arms around waist from behind, fist above navel, pull inward-and-upward 5 times.",
            "4. BACK BLOWS: Alternate 5 firm back blows between shoulder blades with 5 abdominal thrusts.",
            "5. IF UNCONSCIOUS: Strap to CMRS board, inspect mouth for visible object, and start Microgravity CPR."
        ]
    },
    "PNEUMOTHORAX": {
        "title": "[EMERGENCY] PNEUMOTHORAX (Collapsed Lung) - ISS Checklist JSC-48522",
        "steps": [
            "1. 100% OXYGEN: Apply Non-Rebreather Mask at 15 L/min immediately.",
            "2. ULTRASOUND CHECK: Scan front chest with Butterfly iQ+ probe; missing 'lung sliding' confirms collapsed lung.",
            "3. NEEDLE DECOMPRESSION (If severe dyspnea / swollen neck veins): Clean 2nd rib space (mid-clavicular) or 4th/5th (axillary).",
            "4. RELEASE AIR: Insert 14G catheter-over-needle just ABOVE the rib until air hisses out; remove metal needle, tape tube, attach one-way valve."
        ]
    },
    "CPR": {
        "title": "[EMERGENCY] MICROGRAVITY CPR (Cardiac Arrest) - ISS Checklist JSC-48522",
        "steps": [
            "1. CALL CREW & DEPLOY AED: Alert Crew Medical Officer and bring AED + Oxygen Bag-Valve-Mask (BVM).",
            "2. ZERO-G POSITION: Use Handstand Method (feet braced on opposite ceiling/wall) or Strapped CMRS Board Method.",
            "3. COMPRESSIONS: Push hard & fast on center of sternum at 100-120/min (5-6 cm depth), allowing full recoil.",
            "4. BREATHS (30:2): Give 2 BVM breaths with 100% O2 after every 30 compressions.",
            "5. DEFIBRILLATE: Attach AED pads immediately, clear crew during shock, and resume compressions."
        ]
    },
    "SEPSIS_INFECTION": {
        "title": "[EMERGENCY] SEPSIS / SYSTEMIC INFECTION - ISS Checklist JSC-48522",
        "steps": [
            "1. LOCATE SOURCE: Inspect skin wounds/rash (#12), urine strip (#5), and blood CBC/CRP (#1, #3).",
            "2. EARLY ANTIBIOTICS: Administer broad-spectrum Ertapenem 1g IM/IV or Levofloxacin 500mg PO/IV per Flight Surgeon.",
            "3. IV FLUIDS: Give Normal Saline bolus (500-1000 mL) and monitor vitals every 30 minutes."
        ]
    },
    "RENAL_STONE_COLIC": {
        "title": "[EMERGENCY] ACUTE KIDNEY STONE ATTACK (Renal Colic) - ISS Checklist JSC-48522",
        "steps": [
            "1. PAIN RELIEF: Give Ketorolac (Toradol) 30 mg IM/IV (or Ibuprofen 600 mg PO).",
            "2. NAUSEA & STONE PASSAGE: Give Ondansetron 4-8 mg melt-tablet + Tamsulosin (Flomax) 0.4 mg PO.",
            "3. ULTRASOUND: Scan kidney/bladder with Butterfly iQ+ to check for ureteral blockage."
        ]
    },
    "UROSEPSIS_UTI": {
        "title": "[EMERGENCY] ACUTE UTI / URINARY RETENTION - ISS Checklist JSC-48522",
        "steps": [
            "1. BLADDER ULTRASOUND: Check bladder volume (>500 mL without voiding indicates zero-G retention).",
            "2. DRAIN BLADDER: If blocked, perform sterile catheterization using ISS Urinary Catheter Kit.",
            "3. ANTIBIOTICS: Start oral Ciprofloxacin 500 mg BID (or Bactrim DS) and hydrate >2.5L/day."
        ]
    },
    "SANS_VTE_THROMBOSIS": {
        "title": "[EMERGENCY] NECK VEIN BLOOD CLOT (IJV Thrombosis) / SANS - ISS Checklist",
        "steps": [
            "1. DOPPLER ULTRASOUND: Scan Internal Jugular Vein (#10) for clot or backward blood flow.",
            "2. STOP HEAVY STRAINING: Avoid Valsalva breath-holding to prevent clot embolization.",
            "3. ANTICOAGULATION & LBNP: Start Enoxaparin SC / Apixaban PO per Flight Surgeon and deploy LBNP."
        ]
    },
    "CO2_TOXIC_INHALATION": {
        "title": "[EMERGENCY] HIGH CABIN CO2 / HYPERCAPNIA - ISS Checklist JSC-48522",
        "steps": [
            "1. OXYGEN MASK: Put astronaut on 100% O2 Portable Breathing Apparatus immediately.",
            "2. VENTILATE: Move to high-airflow module, turn on portable fans, and check CDRA CO2 scrubber."
        ]
    }
}
# Universal first steps: prepended to EVERY protocol response and to the "no protocol matches" response.
# User-facing text always writes "Crew Medical Officer" in full (see GLOSSARY.md, docs/adr/0004).
UNIVERSAL_FIRST_STEPS = [
    "S1. SCENE SAFETY: Make sure you and the Patient are away from immediate danger (toxic air, smoke, fire, moving equipment, exposed power). Remove whatever may have triggered this, or move the Patient away from it: food, an allergen, a chemical, a gas leak, a medication, or a piece of equipment. Move the Patient only if staying is more dangerous.",
    "S2. CALL THE CREW MEDICAL OFFICER: Call the Crew Medical Officer to the scene now. Keep following the steps below until the Crew Medical Officer takes over."
]

# Fixed severity per protocol. A response's severity is the highest among its matched protocols.
# "life_threatening" outranks "urgent". GCS never changes severity.
PROTOCOL_SEVERITY = {
    "CPR": "life_threatening",
    "CHOKING": "life_threatening",
    "ANAPHYLAXIS": "life_threatening",
    "PNEUMOTHORAX": "life_threatening",
    "CO2_TOXIC_INHALATION": "life_threatening",
    "CHEST_PAIN": "urgent",
    "PSYCHOSIS": "urgent",
    "SEPSIS_INFECTION": "urgent",
    "RENAL_STONE_COLIC": "urgent",
    "UROSEPSIS_UTI": "urgent",
    "SANS_VTE_THROMBOSIS": "urgent"
}

# Lay-language descriptions used ONLY to improve retrieval (search index). Never shown to the Responder
# and never used as instructions. Written for this prototype; review and tune with the eval set.
RETRIEVAL_DESCRIPTIONS = {
    "ANAPHYLAXIS": "allergic reaction after food, medicine, sting or chemical; lips, tongue, face or throat swelling; throat tight; hives, itchy raised rash; wheezing; dizzy, faint",
    "PSYCHOSIS": "strange or aggressive behaviour; paranoid, hearing voices, seeing things; agitated, threatening crew; confused speech; danger to self or others",
    "CHEST_PAIN": "chest pain, pressure or tightness; pain spreading to arm, jaw or back; sweating, nausea; heart attack; palpitations",
    "CHOKING": "food or object stuck in throat; cannot talk, breathe or cough; clutching throat; noisy high-pitched breathing; turning blue",
    "PNEUMOTHORAX": "sudden sharp one-sided chest pain; suddenly very short of breath, cannot catch breath; collapsed lung; bulging neck veins; after chest injury",
    "CPR": "collapsed, unconscious, not responding, not breathing or only gasping; no pulse; cardiac arrest; lifeless",
    "SEPSIS_INFECTION": "infection with signs of serious illness: confused or drowsy, very fast heartbeat or breathing, pale grey or mottled skin, shivering with high fever and very weak; infected wound red, hot, spreading, pus. Not a simple cold, flu or sore throat",
    "RENAL_STONE_COLIC": "severe pain in side or back coming in waves, spreading to groin; blood in urine; restless, cannot sit still; nausea, vomiting",
    "UROSEPSIS_UTI": "burning when peeing; cannot pee, bladder full; peeing often; cloudy or smelly urine; lower belly pain; fever with urinary symptoms",
    "SANS_VTE_THROMBOSIS": "swelling, pain or tenderness on one side of the neck; neck vein clot; blurred or changed vision; headache with face fullness",
    "CO2_TOXIC_INHALATION": "headache, dizziness, breathing fast, drowsy; several crew affected in the same module; stuffy air; CO2 alarm; fumes, smoke or toxic gas",
}
