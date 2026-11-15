# checks.md: Check catalogue for the MADA agent.
# The agent may ONLY ask the Responder for Checks listed here (docs/adr/0003).
# "status": "SOURCED" means the criteria are copied from the cited source.
#           "UNVALIDATED" means a placeholder written for this prototype, to be replaced by the
#           detailed detection protocol when it arrives. Numeric answers are only checked for
#           physical plausibility and never set severity.
#
# GCS criteria: "GLASGOW COMA SCALE: Do it this way" aid, Institute of Neurological Sciences
# NHS Greater Glasgow and Clyde, (c) Sir Graham Teasdale 2015,
# https://www.glasgowcomascale.org/downloads/GCS-Assessment-Aid-English.pdf
# Reporting and escalation rules: https://www.glasgowcomascale.org/faq/ (NICE CG176 criteria quoted there).
# Reuse beyond this prototype should be confirmed with the Royal College of Physicians and Surgeons of Glasgow.

CHECK_CATALOGUE = {
    "GCS": {
        "title": "Glasgow Coma Scale (eyes, speech, movement)",
        "status": "SOURCED",
        "source": "GCS 'Do it this way' aid (c) Sir Graham Teasdale 2015; glasgowcomascale.org",
        "when": "Ask when the Responder is not the Patient and the Patient is not clearly alert and talking.",
        "instruction": "CHECK for anything that stops the Patient seeing, speaking or moving (an injury, swelling, a mask). OBSERVE the eyes, what the Patient says, and how both arms move. STIMULATE only if needed: first speak or shout a request; if there is no response, press firmly on a fingertip; if there is still no response, pinch the muscle at the top of the shoulder (trapezius) or press the notch above the eye (supraorbital notch). RATE each part by the BEST response you saw.",
        "answer": {
            "type": "gcs",
            "components": {
                "eye": [
                    {"score": 4, "rating": "Spontaneous", "criterion": "Open before stimulus"},
                    {"score": 3, "rating": "To sound", "criterion": "After spoken or shouted request"},
                    {"score": 2, "rating": "To pressure", "criterion": "After finger tip stimulus"},
                    {"score": 1, "rating": "None", "criterion": "No opening at any time, no interfering factor"},
                    {"score": "NT", "rating": "Non testable", "criterion": "Closed by local factor"}
                ],
                "verbal": [
                    {"score": 5, "rating": "Orientated", "criterion": "Correctly gives name, place and date"},
                    {"score": 4, "rating": "Confused", "criterion": "Not orientated but communication coherently"},
                    {"score": 3, "rating": "Words", "criterion": "Intelligible single words"},
                    {"score": 2, "rating": "Sounds", "criterion": "Only moans / groans"},
                    {"score": 1, "rating": "None", "criterion": "No audible response, no interfering factor"},
                    {"score": "NT", "rating": "Non testable", "criterion": "Factor interferring with communication"}
                ],
                "motor": [
                    {"score": 6, "rating": "Obeys commands", "criterion": "Obey 2-part request"},
                    {"score": 5, "rating": "Localising", "criterion": "Brings hand above clavicle to stimulus on head neck"},
                    {"score": 4, "rating": "Normal flexion", "criterion": "Bends arm at elbow rapidly but features not predominantly abnormal"},
                    {"score": 3, "rating": "Abnormal flexion", "criterion": "Bends arm at elbow, features clearly predominantly abnormal"},
                    {"score": 2, "rating": "Extension", "criterion": "Extends arm at elbow"},
                    {"score": 1, "rating": "None", "criterion": "No movement in arms / legs, no interfering factor"},
                    {"score": "NT", "rating": "Non testable", "criterion": "Paralysed or other limiting factor"}
                ]
            },
            "flexion_features": {
                "abnormal": "Slow, stereotyped; arm across chest; forearm rotates; thumb clenched; leg extends",
                "normal": "Rapid; variable; arm away from body"
            }
        }
    },
    "RESPONSIVENESS": {
        "title": "Does the Patient respond?",
        "status": "UNVALIDATED",
        "source": "placeholder",
        "instruction": "Speak loudly to the Patient and tap their shoulder. Choose what best describes them.",
        "answer": {"type": "choice", "options": ["alert_and_talking", "responds_to_voice", "responds_only_to_touch", "no_response"]}
    },
    "NORMAL_BREATHING": {
        "title": "Is the Patient breathing normally?",
        "status": "UNVALIDATED",
        "source": "placeholder",
        "instruction": "Look at the chest and listen at the mouth for up to 10 seconds. Occasional gasps are NOT normal breathing.",
        "answer": {"type": "choice", "options": ["normal", "abnormal_or_gasping", "not_breathing"]}
    },
    "SPEAK_OR_COUGH": {
        "title": "Can the Patient speak or cough?",
        "status": "UNVALIDATED",
        "source": "placeholder (CHOKING step 1 refers to forceful coughing or speaking)",
        "instruction": "Ask the Patient to say their name, or to cough.",
        "answer": {"type": "choice", "options": ["speaks_normally", "coughs_forcefully", "weak_or_silent_cough", "cannot_speak_or_cough"]}
    },
    "BREATHING_DIFFICULTY": {
        "title": "How hard is it for the Patient to breathe?",
        "status": "UNVALIDATED",
        "source": "placeholder; PNEUMOTHORAX step 3 names severe dyspnea",
        "instruction": "Ask the Patient to tell you how they feel in one sentence, and watch how they breathe.",
        "answer": {"type": "choice", "options": ["no_difficulty", "mild_speaks_full_sentences", "moderate_short_phrases_only", "severe_single_words_or_cannot_speak"]}
    },
    "NECK_VEINS": {
        "title": "Are the veins on the side of the neck bulging?",
        "status": "UNVALIDATED",
        "source": "placeholder; PNEUMOTHORAX step 3 names swollen neck veins",
        "instruction": "Look at both sides of the Patient's neck. If you can, take a photo of the neck.",
        "answer": {"type": "choice", "options": ["not_bulging", "bulging", "unsure"], "accepts_image": True}
    },
    "CHEST_PAIN": {
        "title": "Does the Patient have chest pain?",
        "status": "UNVALIDATED",
        "source": "placeholder",
        "instruction": "Ask the Patient whether they have pain or pressure in the chest, and where.",
        "answer": {"type": "choice", "options": ["no", "yes"], "accepts_text": True}
    },
    "PULSE_COUNT": {
        "title": "Pulse count",
        "status": "UNVALIDATED",
        "source": "placeholder",
        "instruction": "Find the pulse at the wrist (thumb side) or the side of the neck. Count the beats for 30 seconds and multiply by 2.",
        "answer": {"type": "number", "unit": "beats/min", "plausible": [20, 250]}
    },
    "BREATH_COUNT": {
        "title": "Breath count",
        "status": "UNVALIDATED",
        "source": "placeholder",
        "instruction": "Watch the chest rise. Count the breaths for 30 seconds and multiply by 2.",
        "answer": {"type": "number", "unit": "breaths/min", "plausible": [2, 70]}
    },
    "SKIN_LOOK": {
        "title": "Skin colour, rash or swelling",
        "status": "UNVALIDATED",
        "source": "placeholder",
        "instruction": "Look at the face, lips, neck, chest and arms. Take a clear photo of any rash or swelling in good light.",
        "answer": {"type": "multi_choice", "options": ["normal", "hives_or_raised_rash", "flat_rash", "swelling_face_lips_tongue", "pale_or_grey", "blue_lips"], "accepts_image": True}
    },
    "PAIN": {
        "title": "Pain location and strength",
        "status": "UNVALIDATED",
        "source": "placeholder",
        "instruction": "Ask the Patient where it hurts and how strong the pain is from 0 (none) to 10 (worst imaginable).",
        "answer": {"type": "number", "unit": "0-10", "plausible": [0, 10], "accepts_text": True}
    },
    "BREATHING_SOUND": {
        "title": "Breathing or cough sound",
        "status": "UNVALIDATED",
        "source": "placeholder; audio understanding is unevaluated",
        "instruction": "Hold the phone or tablet about 20 cm from the Patient's mouth and record 10 to 20 seconds of breathing (or coughing).",
        "answer": {"type": "audio", "max_seconds": 30}
    }
}

# Deterministic fast-path rules applied to Check answers (the model can also fast-path from free text
# on the first message, but only to a life_threatening protocol).
FAST_PATH_RULES = [
    {"when": {"RESPONSIVENESS": ["no_response"], "NORMAL_BREATHING": ["abnormal_or_gasping", "not_breathing"]}, "protocol": "CPR"},
    {"when": {"SPEAK_OR_COUGH": ["cannot_speak_or_cough", "weak_or_silent_cough"]},
     "unless": {"RESPONSIVENESS": ["no_response", "responds_only_to_touch"]}, "protocol": "CHOKING"}
]

# When chest pain is present, these Checks must be answered before the agent may finalize
# (distinguishes PNEUMOTHORAX from other chest pain; PNEUMOTHORAX step 3 + clinical note from the project owner).
CHEST_PAIN_REQUIRED_CHECKS = ["BREATHING_DIFFICULTY", "NECK_VEINS"]

# GCS escalation rules (NICE CG176 as quoted in the glasgowcomascale.org FAQ). Compared only on components
# testable (not NT) in both readings.
GCS_ALERT_RULES = [
    {"rule": "drop_eye_or_verbal_ge_3", "description": "Any drop of 3 or more points in the eye-opening or verbal response"},
    {"rule": "drop_motor_ge_2", "description": "A drop of 2 or more points in the motor response"},
    {"rule": "sustained_drop_1_ge_30min", "description": "A sustained (at least 30 minutes) drop of one point in GCS level"}
]
