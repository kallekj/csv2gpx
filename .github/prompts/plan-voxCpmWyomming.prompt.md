# Plan: VoxCPM Wyoming TTS Service

Build a container-first Wyoming text-to-speech service in this repo that wraps VoxCPM for Home Assistant over TCP. The first shippable target is a solid non-streaming Wyoming TTS service with config-driven metadata and model/runtime settings. True Wyoming streaming stays in scope, but only behind a feasibility gate because the public VoxCPM API appears to take complete target text rather than incremental text input.

## Phases

### Phase 1: Runtime and Packaging Foundation

Replace the placeholder CLI with a real async service entrypoint, add runtime dependencies, and define typed config for:
- Host and port (TCP only)
- Model path (local or HuggingFace)
- GPU devices list
- Batching limits (max_num_batched_tokens, max_num_seqs)
- GPU memory utilization target
- Exposed Wyoming metadata (service name, voice name, language, model description)

**Blocks**: all later work.

### Phase 2: VoxCPM Adapter and Audio Normalization

Introduce a model adapter that owns:
- Async VoxCPM server pool lifecycle (from_pretrained, wait_for_ready, generate, stop)
- Exposing model info (sample rate, etc.)
- Converting VoxCPM float32 waveform chunks to mono int16 PCM at the model's native sample rate

**Depends on**: Phase 1.

### Phase 3: Wyoming TCP Service Implementation

Add an async Wyoming server/event-handler layer that:
- Responds to `describe` with `info` containing one logical voice from config
- Handles `synthesize` events by streaming `audio-start`, one or more `audio-chunk`, and `audio-stop`
- Exposes a single voice name/language/model per instance

**Depends on**: Phase 1 and 2.

### Phase 4: True Streaming Feasibility Spike

(Parallel with late Phase 3 test work.)

Verify whether VoxCPM or a lower-level integration can begin audio output before `synthesize-stop`. 

**Pass condition (strict)**: audio must be emitted before the final synthesize-stop event.

If that cannot be proven, the service must not advertise `supports_synthesize_streaming=true`.

**Depends on**: Phase 1 and 2.

### Phase 5: Streaming Follow-up Decision

- **If spike succeeds**: Implement `synthesize-start` / `synthesize-chunk` / `synthesize-stop`, send audio before final stop, and set `supports_synthesize_streaming=true`.
- **If spike fails**: Ship non-streaming first, document the limitation, and keep streaming disabled rather than emulating it poorly.

**Depends on**: Phase 4.

### Phase 6: Container and Docs Hardening

Update the Docker image/runtime assumptions for GPU-backed deployment:
- Document required CUDA/flash-attn prerequisites
- Add CLI examples for Home Assistant Wyoming usage
- Replace scaffold README with service-specific instructions

**Depends on**: Phase 3; incorporate Phase 5 only if streaming is proven.

### Phase 7: Test Coverage to Meet Repo Standards

- Unit tests for config parsing and audio conversion
- Handler tests for `describe` / `synthesize`
- Lifecycle tests around startup/shutdown and VoxCPM adapter failures
- CLI tests for argument validation
- At least one end-to-end Wyoming interaction test (with mocked VoxCPM adapter)
- Coverage must stay above the repo's strict 90% threshold

**Can start alongside** Phase 2 and 3, but finishes after **Phase 6**.

## Relevant Files

- `/home/kj/Documents/VoxCPM-Wyomming/pyproject.toml` — add runtime dependencies, adjust project description
- `/home/kj/Documents/VoxCPM-Wyomming/README.md` — replace scaffold docs with model/runtime prerequisites, container usage, Home Assistant guidance
- `/home/kj/Documents/VoxCPM-Wyomming/Dockerfile` — adapt container for real runtime and GPU-oriented expectations
- `/home/kj/Documents/VoxCPM-Wyomming/Makefile` — keep developer/test commands aligned
- `/home/kj/Documents/VoxCPM-Wyomming/src/voxcpm_wyomming/__main__.py` — convert placeholder entrypoint into service startup/CLI boundary
- `/home/kj/Documents/VoxCPM-Wyomming/src/voxcpm_wyomming/` — add new service modules for config, VoxCPM adapter, Wyoming event handling, and server lifecycle
- `/home/kj/Documents/VoxCPM-Wyomming/tests/test_smoke.py` — replace or expand current smoke check
- `/home/kj/Documents/VoxCPM-Wyomming/tests/` — add new coverage for config, adapter, Wyoming protocol, and lifecycle

## Decisions Locked In

- **Client**: Home Assistant
- **Transport**: TCP only (not stdin, not unix socket)
- **Deployment**: Container-first
- **Baseline feature scope**: Plain text synthesis only (no prompt latents, reference audio, LoRA selection, or other advanced features in v1)
- **Audio output**: Mono int16 PCM at the model's native sample rate
- **Voice metadata**: One logical voice per service, configured at runtime (because VoxCPM does not expose a built-in Wyoming voice catalog)
- **Streaming policy**: Only if audio provably starts before synthesize-stop; otherwise defer and ship non-streaming first

## Main Risk: True Streaming Feasibility

The only material unknown is whether the VoxCPM API or a lower-level integration can emit audio before the final text is known. Your requirement is strict: audio must start before `synthesize-stop`. The public VoxCPM surface found in discovery takes complete `target_text` rather than supporting incremental text ingestion. This is why streaming is treated as a gated spike, not an assumption.

## Further Considerations

1. **Dependency strategy**: Prefer published `nano-vllm-voxcpm` package if stable in the target container; fall back to source-install only if GPU/runtime constraints require it.
2. **Streaming implementation path**: First inspect whether lower-level VoxCPM server/engine APIs accept incremental text safely before considering segmented per-chunk synthesis.
3. **Operational posture**: Model load time and GPU memory footprint will dominate startup; readiness signaling and clear startup logs should be part of the implementation, not an afterthought.

## Approval Gates

If this plan matches your intent, approval enables immediate implementation. If you want changes, the most likely knobs are:

1. Expand v1 beyond plain text synthesis (e.g., add prompt latents, reference audio)
2. Add extra transports beyond TCP
3. Tighten or relax the streaming requirement
