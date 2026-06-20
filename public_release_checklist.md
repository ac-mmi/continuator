# Public Release Checklist

Ordered by dependency (top-to-bottom).

## Phase 0 — Foundation

- [ ] Confirm release branch strategy (`main` vs `release/v0.1`) and align README clone instructions.
- [ ] Confirm Python support policy (>=3.10) and add explicit preflight check in docs.

## Phase 1 — Hugging Face publish (critical path)

- [ ] Create/publish HF repo: `continuator-ai/continuator-v10-lora`.
- [ ] Upload `README.md` model card.
- [ ] Upload `adapter_config.json`.
- [ ] Upload `adapters.safetensors`.
- [ ] Verify repo is publicly accessible (no 404).

## Phase 2 — Repo structure parity with release plan

- [ ] Add `models/` directory.
- [ ] Add `models/README.md` with HF download instructions.
- [ ] Add `models/.gitkeep`.

## Phase 3 — Documentation completion

- [ ] Add `docs/environment.md`.
- [ ] Add `docs/cli-reference.md`.
- [ ] Add `docs/architecture.md`.
- [ ] Update README links to new docs.
- [ ] Add explicit HF failure fallback section in README.

## Phase 4 — Clean-machine runtime verification

- [ ] Fresh clone on Python 3.10+.
- [ ] `pip install -e .` passes.
- [ ] `continuator --help` passes.
- [ ] `continuator continue examples/neck.txt` passes.
- [ ] `continuator explain examples/neck.txt` passes.
- [ ] Repeat continue/explain on all example files.

## Phase 5 — Security and path hygiene recheck

- [ ] Verify `.env`, `.env.local`, `.venv`, `node_modules` remain untracked.
- [ ] Scan for token signatures (`sk-`, `ghp_`, `AKIA`, `Bearer`).
- [ ] Scan for local path leaks (`/Users/`, `/home/`, `C:\`).
- [ ] Confirm no absolute symlinks are tracked in git.

## Phase 6 — Final release gate

- [ ] Re-run independent audit and regenerate `release_readiness_report.md`.
- [ ] Confirm zero FAIL items.
- [ ] Tag release and publish GitHub release notes.
