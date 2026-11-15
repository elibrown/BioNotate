# mada-agent

An HTTP service that guides a crew member with **no medical training** (the Responder) through an on-board emergency. It takes a description of what's happening, as text with an optional photo or audio clip. It may ask a few Checks the Responder can do on the spot, such as a pulse count, a photo of a rash, or the Glasgow Coma Scale. It then returns the matching protocol(s) from the ISS Medical Checklist (`rules.md`), **copied word for word**. Every response starts by making the scene safe and calling the **Crew Medical Officer**.

The model is Google's Gemma 4 E2B, run as the official QAT Q4_0 GGUF in llama.cpp. It needs about 3 GB of VRAM, which fits the 6 GB cloud GPU.

Read **Accuracy and limits** before showing this to anyone.

- Integration guide for the web app (request/response, audio, how to render): [`docs/INTEGRATION.md`](docs/INTEGRATION.md)
- Terms: [`GLOSSARY.md`](GLOSSARY.md). Decisions: [`docs/adr/`](docs/adr/)

## How it decides

```
Responder message (+ photo / audio)
  │
  ├─ Check answers validated (impossible values rejected and asked again); GCS components + NICE trend alert
  ├─ deterministic fast-path rules (no response + not breathing → CPR; can't speak/cough → CHOKING)
  ├─ protocol shortlist: vector search (ChromaDB) + every life-threatening protocol
  ├─ Gemma 4 E2B picks protocol IDs / Check IDs only (JSON schema forced by llama-server)
  ├─ code enforces the rules: closed ID lists, chest pain → breathing + neck-vein Checks, GCS, 3-round limit
  └─ response = first steps (scene safety, call the Crew Medical Officer) + verbatim protocol steps
```

The model never writes treatment text ([ADR 0002](docs/adr/0002-verbatim-steps-grounding.md)). If it's down, times out or returns garbage, the service still answers, with `degraded: true` and the protocols found by text search.

## Run

### Docker (cloud GPU)

```bash
python scripts/prepare_models.py    # downloads ~4.4 GB into ./models (GGUF, mmproj, embedding model)
docker compose up -d                # llama-server (CUDA) + mada-agent on :8000
curl localhost:8000/health
```

This needs the NVIDIA Container Toolkit. Before deploying, pin `LLAMA_CPP_TAG` to a llama.cpp build at or after b12383, the build it was tested on.

### Local (Windows or Linux, for development)

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"     # Linux: .venv/bin/pip
python scripts/prepare_models.py
# llama.cpp release build (Windows: llama-bXXXX-bin-win-cuda-13.5-x64.zip + cudart zip)
llama-server -m models/gemma-4-E2B_q4_0-it.gguf --mmproj models/gemma-4-E2B-it-mmproj.gguf \
             -c 8192 -np 1 -ngl 99 --jinja --port 8080
uvicorn mada_agent.main:app --port 8000          # ONE worker
```

### Configuration (environment variables, or `.env`; see `.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `LLAMA_SERVER_URL` | `http://localhost:8080` | llama-server base URL |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `QUEUE_TIMEOUT_S` / `INFERENCE_TIMEOUT_S` | 30 / 60 | Wait for the model slot (then 503); per-call limit (then degraded) |
| `MAX_ROUNDS` | 3 | Check rounds before the agent must finalize |
| `RETRIEVAL_TOP_K` | 5 | Protocols from vector search |
| `ALWAYS_INCLUDE_LIFE_THREATENING` | true | Always offer CPR, CHOKING, ANAPHYLAXIS, PNEUMOTHORAX and CO2 to the model |
| `MAX_IMAGE_PX` / `MAX_AUDIO_S` / `MAX_UPLOAD_MB` | 896 / 30 / 10 | Media limits |
| `LLM_ENABLE_THINKING` | false | Gemma 4's thinking mode. It's off because the schema's `rationale` field does the reasoning, and thinking makes calls slower. |
| `PROBE_MEDIA` | true | The startup probe also checks image and audio input |

### Try it

```bash
curl -s localhost:8000/api/v1/clinical/analyze \
  -F 'conversation={"turns":[{"role":"responder","timestamp":"2026-11-14T12:00:00Z","text":"he ate a ration bar and his lips are swelling, throat feels tight"}]}'

curl -s localhost:8000/api/v1/clinical/analyze \
  -F 'conversation={"turns":[{"role":"responder","timestamp":"2026-11-14T12:00:00Z","text":"itchy rash after the new antibiotic"}]}' \
  -F image=@rash.jpg -F audio=@description.webm

curl -s localhost:8000/api/v1/clinical/protocols
curl -s localhost:8000/api/v1/clinical/checks
```

Interactive API docs are at `/docs`.

## Knowledge files

- **`rules.md`**: the 11 ISS emergency protocols (verbatim source), `UNIVERSAL_FIRST_STEPS`, `PROTOCOL_SEVERITY`, and `RETRIEVAL_DESCRIPTIONS`. The descriptions are lay-language text used **only** for search and as a "typical presentation" hint to the model, and are never shown to the Responder. The service refuses to start if the file is inconsistent.
- **`checks.md`**: the closed Check catalogue. GCS is `SOURCED` from the official *Glasgow Coma Scale: Do it this way* aid. Every other Check is an `UNVALIDATED` placeholder until the detailed detection protocol arrives. It also holds the fast-path rules, the chest-pain rule, and the GCS escalation rules (NICE CG176).

Both files are Python literals inside markdown. They are parsed with `ast.literal_eval` and never executed.

**GCS licence note:** the GCS aid is © Sir Graham Teasdale 2015. `checks.md` reproduces its criteria text, with attribution and a link, and none of its illustrations. Confirm reuse with the Royal College of Physicians and Surgeons of Glasgow before any public or commercial deployment.

## Accuracy and limits

> **Status at hand-off: the held-out test split has NOT been run yet.** All numbers below come from the **dev**
> split, the one used to tune the prompt, so they are optimistic. Before anyone relies on accuracy, freeze a
> prompt version and run `python eval/run_eval.py --source all --split test`, then replace this table.

Gemma 4 E2B Q4_0 on an RTX 5060 Laptop (8 GB). llama.cpp b12383, 8K context. About 2.9 GB VRAM. About 1.5 s per model call.

| Prompt | Eval set (dev) | Missed life-threatening | Fast-path recall | Protocol-set accuracy | Invalid output |
|---|---|---|---|---|---|
| v1 | synthetic, 12 cases | 1 of 5 | 60% | 83% | 0% |
| v1 | DDXPlus, 181 cases | 1 of 60 | n/a | 60% | 0% |
| v2 | synthetic, 12 cases | 0 of 5 | 100% | 100% | 0% |
| v2 | DDXPlus, 181 cases | 2 of 60 | n/a | 65% | 0% |
| **v3 (shipped)** | synthetic, 12 cases | 0 of 5 | 80% | 100% | 0% |
| v3 | DDXPlus | not finished | | | |

What the DDXPlus runs showed:
- **Positive cases** (anaphylaxis, pneumothorax, chest pain) are found about 87% of the time.
- **Benign illnesses are over-triaged.** With v2, only about 40% of colds, flu and pharyngitis cases correctly got "no protocol"; most were called SEPSIS_INFECTION. Hay fever was sometimes called ANAPHYLAXIS. v3 adds an explicit rule and a sharper SEPSIS description in `rules.md` for this, but they haven't been measured on DDXPlus yet.
- **The misses were pneumothorax called chest pain**, when the Responder couldn't do the neck-vein and breathing Checks. v3 tells the model to give both protocols when pneumothorax can't be ruled out.
- By the agreed ranking, missed life-threatening cases come first, so **v2 counted as worse than v1** on DDXPlus (2 vs 1 of 60, small numbers). v3 still has to show it isn't worse than v1 before it's frozen.

What these numbers do **not** tell you:
- **No real patients, no astronauts, no microgravity.** The synthetic scenarios were written for this project. DDXPlus is a synthetic patient generator (CC BY 4.0), rendered into text by fixed templates. Real Responders under stress will write differently.
- **Images and audio are unevaluated for accuracy.** No public dataset matched these protocols. The startup probe only proves the model *accepts* images and audio. Whatever the model sees or hears is reported as unconfirmed and never decides anything alone.
- **Checks other than GCS are placeholders.** Their options and plausibility ranges are not clinically validated.
- **DDXPlus covers only 3 of the 11 protocols** (ANAPHYLAXIS, PNEUMOTHORAX, CHEST_PAIN). The other protocols are tested only by the small synthetic set.
- The service is decision support for the minutes before the Crew Medical Officer arrives. It doesn't replace them, and every response says so.

## Tests and eval

```bash
pytest                                                    # unit + API tests (model server mocked)
python eval/ddxplus_build.py                              # builds eval/cases/ddxplus.jsonl (downloads DDXPlus)
python eval/run_eval.py --source synthetic --split dev    # needs a running llama-server
python eval/run_eval.py --source all --split test         # held-out: only on a frozen PROMPT_VERSION
```

Prompt changes are made against the **dev** split only, ranked by:
1. missed life-threatening protocols
2. fast-path recall
3. protocol-set accuracy
4. invalid-output rate
5. median rounds

A version that improves a lower metric at the cost of a higher one is worse. `PROMPT_VERSION` is returned in every response; store it with the result.

## Contents

```
rules.md, checks.md             clinical knowledge (data, reviewed by the project owner)
src/mada_agent/                 the package: main.py (app), routers/clinical.py, agent_service.py (loop),
                                prompt_templates.py, llm_client.py, ingest_service.py (ChromaDB),
                                knowledge.py, checks.py, gcs.py, media.py, schemas.py, config.py
tests/                          pytest suite (no GPU needed)
eval/                           scenarios, DDXPlus builder, runner, results
scripts/prepare_models.py       downloads the model files
docs/INTEGRATION.md, docs/adr/  integration guide, decision records
Dockerfile, docker-compose.yml  cloud deployment
```

Data attribution: DDXPlus, Fansi Tchango et al. (NeurIPS 2022), CC BY 4.0, https://figshare.com/articles/dataset/DDXPlus_Dataset_English_/22687585.
