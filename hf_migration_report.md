# HF Migration Report — Runtime Path Audit

Audit date: 2026-06-20  
Repository audited: `/Users/acmmi/projects/continuator-release`  
Goal: identify every location that must rely on HF model repo (not local research paths)

---

## Executive summary

Runtime code in the release workspace is **already HF-first** via `continuator_engine/adapter_loader.py`.

No release-runtime references to `archive/training-data` were found.

Remaining work is primarily:
1. Publish HF repo (`continuator-ai/continuator-v10-lora`)
2. Draft/upload model card + license in HF bundle
3. Update docs/scaffold gaps (`models/`, missing docs)
4. Re-run clean-machine verification

---

## Search results by pattern

### `/Users/`

| Location | Type | Action required |
|----------|------|-----------------|
| `continuator/console.py:491` | Path redaction regex (`re.sub(r"/Users/[^\s]+", ...)`) | ✅ No migration needed (sanitizer, not a hardcoded dependency) |
| Planning/audit docs (`huggingface_release_checklist.md`, etc.) | Documentation examples | ⚠️ Keep as internal ops docs or replace with neutral `/path/to/...` before public push |
| Local `.venv` symlink (untracked) | Environment artifact | ✅ Not in git; exclude from release artifacts |

**Runtime code hardcoded local paths:** none found.

---

### `archive/training-data`

| Location | Found? | Action |
|----------|--------|--------|
| `continuator_engine/*` | No | ✅ Already migrated |
| `continuator/*` | No | ✅ Already migrated |
| docs/README in release repo | No direct references | ✅ |

**Conclusion:** release runtime no longer depends on research archive paths.

---

### Hardcoded model paths

| Location | Current behavior | HF migration status |
|----------|------------------|---------------------|
| `continuator_engine/adapter_loader.py:7-9` | Defaults: `continuator-ai/continuator-v10-lora`, `continuator-ai/continuator-v9-lora` | ✅ HF repo ids configured |
| `continuator_engine/adapter_loader.py:70-85` | `snapshot_download(...)` to cache dir | ✅ HF download path implemented |
| `continuator_engine/memory_model_v1.py:28-32` | `ensure_adapter(model)` | ✅ Uses HF loader |
| `continuator_engine/memory_extractor_v1.py:429-448` | `_adapter_path()` -> `default_adapter_for_model()` / `ensure_adapter("v10")` | ✅ Uses HF loader |
| `continuator/runtime.py:52-56` | Defaults backend/model env | ✅ No local adapter path |

**Action:** publish the configured HF repo so defaults resolve at runtime.

---

### Local adapter override paths (`MEMORY_EXTRACTOR_ADAPTER_PATH`)

These are intentional overrides (for offline/dev), not blockers:

| Location | Purpose | Keep? |
|----------|---------|-------|
| `continuator_engine/adapter_loader.py:57-64` | Explicit local adapter directory override | ✅ Keep (support/debug) |
| `continuator_engine/memory_model_v1.py:192,200` | Context manager sets adapter path during model switch | ✅ Keep |
| `README.md`, `docs/installation.md`, `.env.example` | User docs for local path override | ✅ Keep |
| `continuator_engine/memory_extractor_v1.py:30` | Comment documenting override env var | ✅ Keep |

No code changes required for migration; ensure docs clearly position HF as default and local path as optional override.

---

### Adapter symlinks

| Location | Finding | Required action |
|----------|---------|-----------------|
| Research ckpt dir `adapters_memory_v10_probe_ckpt_050/adapters.safetensors` | Absolute symlink to local research path | ❌ Do not publish symlink bundle |
| HF upload staging | Must use concrete `0000050_adapters.safetensors` copied as `adapters.safetensors` | ✅ Required at publish time |
| Runtime download (`snapshot_download`, `local_dir_use_symlinks=False`) | Avoids symlink dependence | ✅ Already safe |

---

## Locations that must switch to HF repo (checklist)

### Must be true at launch

- [ ] HF repo `continuator-ai/continuator-v10-lora` exists publicly
- [ ] Default repo id in `adapter_loader.py` matches published repo
- [ ] Docs/README default repo id matches published repo
- [ ] Clean-machine run succeeds with **no** `MEMORY_EXTRACTOR_ADAPTER_PATH`

### Optional / non-blocking references to update later

- [ ] `continuator-ai/continuator-v9-lora` (referenced for v9 mode; not required for v0.1 default)
- [ ] Internal planning docs that still mention local research absolute paths

---

## Residual migration risks

1. **HF repo unpublished** → runtime fails with 404 (current critical blocker).
2. **Wrong checkpoint uploaded** (`adapters.safetensors` != ckpt 050) → quality/regression risk.
3. **Model card/license missing on HF** → publication readiness fail (legal/discoverability).
4. **`adapter_config.json` training metadata** (`data`, `adapter_path`) → not runtime-breaking, but should be sanitized in published artifact.

---

## Migration verdict

**Code migration status:** ✅ Complete (HF-first runtime already in place)  
**Publication migration status:** ❌ Incomplete (HF repo + model card/license not published)
