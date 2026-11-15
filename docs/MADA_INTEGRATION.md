# Model 3 — MADA integration (prototype)

The MADA handoff is integrated into AstroHealth as a **separate** model service.
The original handoff code, knowledge files, and tests are included unchanged in
`services/mada/`, except the Compose port is bound to localhost (`8010`) to
avoid clashing with AstroHealth's `8000` and accidentally exposing an
unauthenticated clinical service.

## What this adds

- `GET /mada`: dedicated emergency-assessment UI supporting text, photo, short
  browser audio, multi-round Checks, GCS entry, and exact protocol display.
- `POST /api/mada/assess`: server-side, multipart proxy to MADA's
  `POST /api/v1/clinical/analyze` (full conversation retained on each round).
  Every request also includes a server-generated, bounded `patient_context`:
  the registered Patient ID, a Patient/Responder identity flag, and at most 12 source-labeled, timestamped latest
  metric values, observation counts, and numeric first-to-last differences.
  This is **not** a new MADA biomarker model or a medical interpretation.
- `GET /api/mada/checks` and `/api/mada/protocols`: server-side catalog proxy.
- `GET /api/patients`: patients from the **existing** `astronauts` roster.
- `GET /api/patients/{id}/trends`: descriptive stored measurement history,
  grouped by `(model/source, metric, unit)`. Video readings from one prediction
  are combined into **one independent observation** (median). Comparisons
  describe numerical change, never improvement or deterioration.
- `mada_assessments` in the existing `astrohealth.db`, with mandatory
  `patient_id` foreign key to `astronauts(id)` and optional `responder_id`.
  Keeps the MADA text/Check conversation and the full last response for
  follow-up. Binary image/audio data is not saved by this integration.
- `GET /api/patients/{id}/mada-assessments` and
  `GET /api/mada/assessments/{id}` for history and resume.

The Patient context is built from `patient_id` on the server, **not from a
browser-supplied measurement payload**. It does not include the patient's
name, raw recordings, freeform notes, or full measurement history. Historical
values may be old or unvalidated; MADA must treat them as supplementary
context only, never a replacement for the Responder's report or emergency Checks.
The UI reports how many metrics were forwarded on a successful response.

**Patient is not the same as Responder.** A-01 can be answering the Checks for
A-02, but the assessment remains linked to Patient A-02.

## Development setup on Windows

1. Start the MADA model server from `services/mada/` according to its
   `README.md` and `docs/INTEGRATION.md`. It requires separately downloaded
   Gemma 4 weights, an embedding model, and a GPU-compatible llama.cpp server.
   `python scripts/prepare_models.py` downloads the weights; do **not** commit
   the `models` directory. The included Docker Compose file binds the MADA
   FastAPI port to `http://127.0.0.1:8010` and requires NVIDIA GPU Docker
   support. The llama.cpp server is internal to that Compose network.
2. In a *new* PowerShell window, activate the existing AstroHealth venv:

   ```powershell
   cd "$HOME\Documents\astro-health-monitor\backend"
   .\.venv\Scripts\Activate.ps1
   $env:MADA_SERVICE_URL = "http://127.0.0.1:8010"
   $env:MADA_DEMO_ENABLED = "1"
   python -m uvicorn app.main:app --reload
   ```

3. Open `http://127.0.0.1:8000/mada`. Select a roster Patient, describe the
   emergency, submit, answer requested Checks, and review the saved case and
   historical measurements. If MADA is unreachable, the UI displays the
   backend error; first steps are cached when the protocols endpoint was
   previously accessible. Run `python -m pytest -q` in `backend/`.

**Without the Gemma/llama.cpp service** the UI and trends are still browsable,
but live MADA inference is not available. Backend integration tests replace
MADA with a mock, so they require neither the weights nor a GPU.

## Deployment/security blockers

The current GitHub Action deploys **only the AstroHealth CPU Dockerfile**. It
will not deploy the new MADA GPU service automatically. A team member must
provision a separate private model service and configure `MADA_SERVICE_URL`.

**Never enable `MADA_DEMO_ENABLED=1` on the public Cloud Run deployment as-is.**
AstroHealth currently lacks end-user authentication and access control. MADA
retains sensitive assessment text, and its endpoints must not be public for
real patients. Before public access, implement authentication, per-patient
access permissions, transport protection, rate limits, retention/deletion,
and audit logging. The flag defaults to disabled to avoid exposing new case
history after a routine merge.

**Database durability is also a blocker:** the current Cloud Run deployment
uses `ASTROHEALTH_DB=/tmp/astrohealth.db`, which is ephemeral and may reset on
restart/redeployment. The existing seeded roster is useful for a demo but is
not durable patient storage. Replace it with a shared durable database such
as Cloud SQL (with a migration) and consider encrypted object storage for any
future media, before claiming that cloud assessment history is persistent.

Clinical limitations from the MADA handoff also apply: the held-out accuracy
test is pending, image/audio interpretation is unevaluated, and most Checks
are unvalidated placeholders. Display the service's `first_steps` and
protocol `steps` verbatim. In an actual emergency contact the Crew Medical
Officer; this is not a clinical device.

The MADA handoff includes GCS criteria subject to separate reuse/licensing
review before public or commercial deployment.
