# Documentation Gap Report

Baseline compared: `release_plan.md` target docs vs actual repository docs.

## Expected vs actual

Expected in `docs/`:
- `installation.md` ✅ present
- `cli-reference.md` ❌ missing
- `environment.md` ❌ missing
- `architecture.md` ❌ missing
- `tui-redesign.md` ✅ present

Gap summary:
- 3 core docs missing.
- README currently absorbs partial content but lacks depth and single-purpose references.

---

## Missing doc 1: `cli-reference.md`

Purpose:
- Authoritative command and flag reference for CLI users.

Proposed table of contents:
1. Overview
2. Global usage and command discovery
3. `continuator continue`
   - purpose
   - args/options
   - examples
   - output format notes
4. `continuator explain`
   - purpose
   - differences from continue mode
   - examples
5. `continuator export`
   - targets (`claude`, `chatgpt`, `gemini`, `markdown`)
   - output filenames
6. `continuator inspect`
7. `continuator benchmark`
8. Exit codes and common errors
9. Automation-friendly usage patterns

---

## Missing doc 2: `environment.md`

Purpose:
- Single source for env vars, defaults, and backend/model behavior.

Proposed table of contents:
1. Environment strategy
2. Required vs optional variables
3. Model resolution variables
   - `MEMORY_EXTRACTOR_HF_REPO`
   - `MEMORY_EXTRACTOR_ADAPTER_PATH`
   - `CONTINUATOR_MODEL_CACHE`
   - `HF_TOKEN`
4. Backend variables
   - `MEMORY_EXTRACTOR_BACKEND`
   - `MEMORY_MODEL`
   - profile/token limits
5. Recommended configs by platform
   - macOS (mlx)
   - cross-platform (transformers)
   - CI/mock mode
6. Security guidance (do not commit `.env`)
7. Troubleshooting matrix

---

## Missing doc 3: `architecture.md`

Purpose:
- Explain internals enough for maintainers and contributors.

Proposed table of contents:
1. System overview
2. Package layout
   - `continuator/`
   - `continuator_engine/`
3. End-to-end flow
   - transcript input
   - chunking/ranking
   - extraction
   - continue/explain rendering
4. Adapter loading and Hugging Face dependency
5. Backend execution paths (`mock`, `mlx`, `transformers`)
6. Test strategy and quality gates
7. Known limitations
8. Release architecture constraints (no bundled weights)

---

## Priority order

1. `environment.md` (unblocks model/run troubleshooting)
2. `cli-reference.md` (unblocks user self-service)
3. `architecture.md` (unblocks contributor maintainability)

## Acceptance criteria

- [ ] README links to all three docs.
- [ ] Commands and env vars match current code behavior.
- [ ] First-time user can run examples without external/internal tribal knowledge.
