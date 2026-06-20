# Launch Checklist

Goal: **Publish model → run one final audit → push GitHub repo**  
Audit/planning only (no implementation in this document)

---

## Phase 1 — Model publication (critical path)

- [ ] Draft HF model card (`README.md`) for `continuator-v10-lora`
- [ ] Prepare clean upload bundle (concrete files, no symlinks)
- [ ] Include `adapter_config.json` (ckpt 050 compatible)
- [ ] Include `adapters.safetensors` (from `0000050_adapters.safetensors`)
- [ ] Include `LICENSE` (MIT)
- [ ] Create HF repo: `continuator-ai/continuator-v10-lora`
- [ ] Upload all model files
- [ ] Verify public repo metadata (files present, no 404)
- [ ] Verify anonymous download works
- [ ] Verify clean-machine inference:
  - [ ] `continuator continue examples/neck.txt`
  - [ ] `continuator explain examples/neck.txt`

Dependency: none (start here)

---

## Phase 2 — Repository publication readiness (parallel where possible)

- [ ] Add `models/` scaffold (`models/README.md`, `.gitkeep`) — if still missing
- [ ] Add missing docs:
  - [ ] `docs/environment.md`
  - [ ] `docs/cli-reference.md`
  - [ ] `docs/architecture.md`
- [ ] Align README branch instructions (`main` vs `release/v0.1`)
- [ ] Ensure README links to HF model repo and troubleshooting for HF 404

Dependency: can start before HF, but final sign-off depends on Phase 1 success

---

## Phase 3 — Final independent audit (required gate)

- [ ] Fresh clone on Python 3.10+
- [ ] `pip install -e .` passes
- [ ] `continuator --help` passes
- [ ] `continuator continue examples/*.txt` passes (all examples)
- [ ] `continuator explain examples/*.txt` passes (all examples)
- [ ] Path leak scan (`/Users/`, `archive/training-data`, absolute symlinks in tracked files)
- [ ] Secret scan (`sk-`, `ghp_`, `AKIA`, `Bearer`)
- [ ] Git size audit (no tracked file >50MB)
- [ ] Regenerate `release_readiness_report.md` with zero FAIL items

Dependency: Phase 1 complete

---

## Phase 4 — GitHub push / release

- [ ] Confirm target branch (`release/v0.1` or `main`)
- [ ] Commit publication docs/checklists (optional)
- [ ] Push public GitHub repository
- [ ] Create GitHub release tag `v0.1.0`
- [ ] Publish release notes linking HF model repo + install/run commands
- [ ] Post-release smoke test from GitHub clone (not local path clone)

Dependency: Phase 3 pass

---

## Go / No-Go criteria

### Go for public beta if:

- HF model published and downloadable anonymously
- Clean-machine continue/explain succeed without local adapter override
- Final audit has no CRITICAL failures

### Go for public release if:

- All public beta criteria met, **and**
- Missing docs/scaffold gaps closed
- Final audit has no FAIL items (CRITICAL/HIGH)
- First-time README-only user path succeeds end-to-end

---

## Suggested owners

| Phase | Owner |
|-------|-------|
| Phase 1 (HF publish) | Model Release Owner |
| Phase 2 (docs/scaffold) | Docs + Repo Maintainer |
| Phase 3 (final audit) | Release QA Owner |
| Phase 4 (GitHub launch) | Repo Maintainer |

---

## Estimated timeline

- Phase 1: 3–6 hours
- Phase 2: 4–8 hours
- Phase 3: 1–2 hours
- Phase 4: 1 hour

Total to launch: **~1–2 working days** depending on model card drafting and doc completion.
