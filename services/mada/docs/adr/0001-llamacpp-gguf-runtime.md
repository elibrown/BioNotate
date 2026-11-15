# Run Gemma 4 E2B as Google's QAT Q4_0 GGUF in llama.cpp, not in transformers

The service runs on a cloud GPU with about 6 GB of VRAM and must accept both images and audio. The bf16 weights alone are about 10 GB, so the plan of trying bf16 and falling back to int4 was dropped. Google's official quantization-aware Q4_0 GGUF (3.35 GB) plus its vision/audio encoder file (`mmproj`, 987 MB) fits in roughly 5–5.5 GB at an 8K context. llama.cpp supports Gemma 4 E2B image input, and audio since PR #21421 (April 2026). The model runs in the official `llama-server` container, and the FastAPI service calls its OpenAI-compatible HTTP API. That keeps the agent code independent of the inference engine.

## Considered Options

- **transformers + bitsandbytes NF4 made locally**: one Python runtime, but Google doesn't document NF4 for Gemma 4, and community reports say quantizing the Per-Layer Embeddings garbles output. It would also need a home-made quality check instead of Google's QAT.
- **vLLM**: lists Gemma 4 E2B audio support, but full-precision weights don't fit in 6 GB. It is the documented fallback if llama.cpp audio turns out to be unreliable. Only the `llm_client` would change.

## Consequences

Image and audio requests must be sent in the formats llama-server accepts (data-URI images, 16 kHz mono WAV, at most 30 s per clip). Whether forcing a JSON schema still works with media attached has to be verified on the pinned llama.cpp build.
