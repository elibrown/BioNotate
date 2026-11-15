# Integrating the MADA clinical agent

This guide is for the web app's backend and frontend developers. It covers what to send, what comes back, and how to show it. Terms such as Responder, Patient, Check and Round are defined in [`GLOSSARY.md`](../GLOSSARY.md).

## How an Assessment works

1. The Responder describes the emergency in text or speech, optionally with a photo.
2. You send the whole conversation so far to `POST /api/v1/clinical/analyze`.
3. The service replies with one of two actions:
   - `action: "ask_checks"`: show the requested Checks, collect the answers, and send the conversation again with the answers appended.
   - `action: "finalize"`: show the protocol(s). The Assessment is done, though the Responder can keep adding information, such as a new GCS.
4. The service allows at most 3 Rounds of Checks, then it finalizes.

**The service is stateless** ([ADR 0005](adr/0005-stateless-conversation.md)). Your app keeps the conversation and sends all of it on every call. The service stores nothing and logs no symptom text, images or audio.

## Request

`POST /api/v1/clinical/analyze` as `multipart/form-data`:

| Field | Required | Content |
|---|---|---|
| `conversation` | yes | JSON string: `{"turns": [Turn, ...]}`, oldest first. The **last turn must be from the responder**. At most 40 turns. |
| `image` | no | A photo for the latest turn: JPEG, PNG, WebP (HEIC if Pillow can read it). At most 10 MB. The service downscales it to 896 px. |
| `audio` | no | Audio for the latest turn: WAV, WebM/Opus, Ogg/Opus, MP3 or M4A. **At most 30 s**, at most 10 MB. |

### Optional Patient context from the application backend

BioNotate can provide a **bounded snapshot of recorded measurements** in the
`conversation` JSON, alongside `turns`, e.g.:

```json
{"turns": [{"role":"responder","timestamp":"2026-11-14T12:00:00Z","text":"my crewmate is dizzy"}],
 "patient_context": {"patient_id":"A-02","responder_is_patient":false,"retrieved_at":"2026-11-14T12:00:01Z",
   "measurements":[{"source":"manual","metric":"hr_bpm","unit":"bpm",
     "latest_value":83,"latest_measured_at":"2026-11-14T11:55:00Z",
     "observation_count":2,"delta_from_first":3,"first_measured_at":"2026-11-13T11:55:00Z"}]}}
```

This field is optional for other clients, and is re-fetched for every BioNotate
assessment turn. It is **supplementary historical context**, not a new Check,
not a Responder statement and not an instruction. `responder_is_patient`
comes from the backend's selected identities: `true` / `false` / `null`
(unknown); never infer it from first-person text. Values may be stale or from
unvalidated models; they cannot independently trigger fast-path protocols. No
patient names, raw media or full history should be transmitted. Only use this
with authorized patients and private service transport.

### Turn

| Field | Turn type | Meaning |
|---|---|---|
| `role` | both | `"responder"` or `"agent"` |
| `timestamp` | both | **Required.** ISO-8601 with a time zone, e.g. `2026-11-14T12:03:10Z`. It is used for GCS trend rules, such as "sustained for 30 minutes", so send the time the message was actually sent. |
| `text` | responder | What the Responder typed, or the transcript if your app transcribes speech. At most 4000 characters. |
| `check_answers` | responder | `{CHECK_ID: answer}` for the Checks the agent asked for. See "Answer formats" below. |
| `asked_check_ids` | agent | Copy `next_checks[].id` from the previous response. |
| `protocol_ids` | agent | Copy `protocols[].id` from the previous response. |

Append one **agent** turn for each response you receive, then the Responder's next turn.

```json
{"turns": [
  {"role": "responder", "timestamp": "2026-11-14T12:00:00Z", "text": "my chest hurts since the treadmill"},
  {"role": "agent", "timestamp": "2026-11-14T12:00:02Z", "asked_check_ids": ["BREATHING_DIFFICULTY", "NECK_VEINS", "PULSE_COUNT"]},
  {"role": "responder", "timestamp": "2026-11-14T12:01:30Z",
   "check_answers": {"BREATHING_DIFFICULTY": "mild_speaks_full_sentences", "NECK_VEINS": "not_bulging", "PULSE_COUNT": 104}}
]}
```

### Answer formats

The full catalogue, with options, units and instructions, comes from `GET /api/v1/clinical/checks`. Build the Check forms from it.

| `answer.type` | Send |
|---|---|
| `choice` | One of `answer.options`, e.g. `"bulging"` |
| `multi_choice` | A list of options, e.g. `["hives_or_raised_rash", "swelling_face_lips_tongue"]` |
| `number` | A number, e.g. `104`. `PAIN` also accepts `{"score": 7, "text": "left flank"}`. |
| `gcs` | `{"eye": 1-4 or "NT", "verbal": 1-5 or "NT", "motor": 1-6 or "NT"}`. Show the criteria from the catalogue next to each level. |
| `audio` | Attach the recording as the request's `audio` file, and send `"recorded"` as the answer value. |

If a Check has `accepts_image: true`, the Responder can attach a photo, for example of a rash or the neck, in the `image` field. An answer outside the physically plausible range, or a value that isn't an allowed option, is **not used**. It comes back in `answer_warnings`, and the Check is asked again.

### Audio from the browser

`MediaRecorder` output (`audio/webm;codecs=opus` in Chrome and Firefox, `audio/mp4` in Safari) can be uploaded as-is. The service converts it to 16 kHz mono WAV for the model. Rules:
- Stop recording at **30 s**. Anything longer is rejected with `413`.
- Send the correct `Content-Type` on the file part. `application/octet-stream` is also accepted.
- Use audio for the Responder **describing** the emergency, or for a **body-sound recording** (breathing, cough, wheeze) when the `BREATHING_SOUND` Check is asked.
- **Audio understanding is unevaluated.** What the model hears is reported as an unconfirmed `observed_feature` and never decides anything on its own.

## Response

```json
{
  "prompt_version": "v2",
  "model_quant": "gemma-4-E2B-it QAT Q4_0 GGUF",
  "degraded": false,
  "action": "finalize",
  "first_steps": ["S1. SCENE SAFETY: ...", "S2. CALL THE CREW MEDICAL OFFICER: ..."],
  "severity": "life_threatening",
  "protocols": [{"id": "ANAPHYLAXIS", "title": "[EMERGENCY] ANAPHYLAXIS ...", "severity": "life_threatening",
                 "steps": ["1. AIRWAY & RESTRAINT: ...", "2. EPINEPHRINE (IMMEDIATE): ..."]}],
  "no_protocol_match": false,
  "message": null,
  "next_checks": [],
  "gcs": {"latest": "E3 V4 M5", "total": 12, "history": [...]},
  "gcs_alert": null,
  "answer_warnings": [],
  "observed_features": ["swollen lips (image)"],
  "rationale": "Rapid lip swelling after food...",
  "decided_by": "model",
  "round": 0,
  "disclaimer": "Decision support only, ..."
}
```

### How to show it, in this order

1. **`gcs_alert`**, if present: a red banner with `gcs_alert.message`, e.g. "Consciousness is getting worse (GCS E4 V5 M6 → E3 V4 M5). Tell the Crew Medical Officer now."
2. **`first_steps`**: always, on every response, at the top. S1 is scene safety, including removing the trigger. S2 is calling the Crew Medical Officer. Write "Crew Medical Officer" in full; never abbreviate it to "CMO" in the UI.
3. If `action == "finalize"`:
   - For each `protocols[]`, show the `title`, a `severity` badge, and the `steps` **exactly as given**. Don't rephrase, summarize or translate them. They are the official checklist text ([ADR 0002](adr/0002-verbatim-steps-grounding.md)).
   - If `no_protocol_match`, show `message`. The Crew Medical Officer must assess.
4. If `action == "ask_checks"`: show `next_checks[]` as forms, with `instruction` as the prompt and the answer widget chosen by `answer.type`. Show `answer_warnings` beside the Checks that have to be measured again.
5. If `degraded`: show `message` prominently. The model was unavailable, and the protocols come from text search only.
6. Keep the **`rationale`** and `observed_features` in a collapsible panel for the Crew Medical Officer. They are model output, not instructions.
7. Show the `disclaimer` in the footer.

`severity` is `life_threatening`, `urgent`, or `null` (nothing chosen yet, or no match). It's the highest severity among the protocols. GCS never changes it.

Show Checks with `status: "UNVALIDATED"` with a small "placeholder" tag until the detailed detection protocol replaces them.

## Errors

| Code | When | What to do |
|---|---|---|
| 400 | Image or audio can't be decoded or is empty | Ask the Responder to retake it |
| 413 | Upload over 10 MB, or audio over 30 s | Shorter recording or smaller photo |
| 415 | Unsupported image or audio type | Convert, or don't attach |
| 422 | `conversation` isn't valid JSON, doesn't match the schema, or the last turn isn't from the Responder | Fix the client |
| 503 | The model slot was busy for more than 30 s (`Retry-After: 5`), or the service is still starting | Retry. Meanwhile, show `first_steps` from `GET /api/v1/clinical/protocols`. |

If the model times out (more than 60 s) or returns unusable output, you get **HTTP 200 with `degraded: true`**, not an error. In an emergency, a response is always better than nothing.

## Other endpoints

- `GET /api/v1/clinical/protocols`: `first_steps` plus all 11 protocols with display steps and severity. Cache it in the app so protocols can be shown offline.
- `GET /api/v1/clinical/checks`: the Check catalogue, including GCS criteria and sources. Build the forms from it.
- `GET /health`: `200` when the model is loaded and has passed the text, image and audio startup probe, `503` otherwise. The body shows `status`, `detail`, the loaded model and context, and which modalities passed.

## Deployment notes for the backend

- **Run one uvicorn worker.** There's one model slot, and requests queue inside the service.
- The service has **no authentication** in v1. Keep it on the private network, reachable only from your backend. Set `CORS_ORIGINS` (comma-separated) if a browser calls it directly.
- Send a `X-Request-ID` header to correlate logs. It is echoed back.
- A typical model call takes 1–3 s on the RTX 5060 test machine. An Assessment usually takes 1–3 calls.
