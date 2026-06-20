# Public Release Blockers

Source of truth: `release_readiness_report.md` (2026-06-20)  
Scope: only FAIL items that block public launch

## CRITICAL

### 1) Hugging Face model repo unavailable (`continuator-ai/continuator-v10-lora`)
- **Description:** Clean-checkout runs of `continuator continue` and `continuator explain` fail with HF 404 because the configured model repo is not published/reachable.
- **Severity:** CRITICAL (hard product failure on default path)
- **Effort estimate:** 3-6 hours (if assets already prepared), 0.5-1 day with validation loop
- **Owner:** Model Release Owner (ML + Release Eng)
- **Resolution steps:**
  1. Create/publish HF model repo `continuator-ai/continuator-v10-lora`.
  2. Upload `README.md` model card, `adapter_config.json`, and `adapters.safetensors`.
  3. Validate anonymous download and authenticated download flows.
  4. Re-run clean-checkout: `continuator continue examples/neck.txt` and `continuator explain examples/neck.txt`.

### 2) Runtime verification FAIL for all examples
- **Description:** `continuator continue examples/*.txt` and `continuator explain examples/*.txt` fail from clean checkout due to unresolved model source.
- **Severity:** CRITICAL (core functionality unavailable)
- **Effort estimate:** 1-2 hours after HF publish
- **Owner:** Release QA Owner
- **Resolution steps:**
  1. Re-run command matrix on fresh machine after HF publish.
  2. Record outputs + timings + exit codes.
  3. Add CI smoke for one example per mode.

## HIGH

### 3) Missing `models/` scaffold required by release plan
- **Description:** `models/`, `models/README.md`, `.gitkeep` missing despite target structure.
- **Severity:** HIGH (documentation/expectation mismatch, onboarding confusion)
- **Effort estimate:** 0.5-1 hour
- **Owner:** Docs + Repo Maintainer
- **Resolution steps:**
  1. Add `models/` directory with `README.md` describing HF download and env vars.
  2. Add `.gitkeep` to retain directory in git without bundling weights.
  3. Cross-link from top-level README.

### 4) Missing planned docs files
- **Description:** `docs/cli-reference.md`, `docs/environment.md`, `docs/architecture.md` absent vs release plan.
- **Severity:** HIGH (incomplete public docs package)
- **Effort estimate:** 4-8 hours total
- **Owner:** Docs Owner + Tech Lead reviewer
- **Resolution steps:**
  1. Draft each doc from existing README + code.
  2. Add command examples, env matrix, architecture diagram/flow.
  3. Link from README and run docs sanity check.

## MEDIUM

### 5) README branch instruction risk (`git checkout release/v0.1`)
- **Description:** First-time users may fail/confuse if branch naming/default branch differs on GitHub.
- **Severity:** MEDIUM
- **Effort estimate:** 15-30 minutes
- **Owner:** Repo Maintainer
- **Resolution steps:**
  1. If launching from `main`, remove branch checkout from quickstart.
  2. If keeping `release/v0.1`, explicitly say "use this only if not default branch".

### 6) README lacks explicit fallback path when HF repo unavailable
- **Description:** Users get blocked at first run without a clearly prioritized fallback flow.
- **Severity:** MEDIUM
- **Effort estimate:** 30-60 minutes
- **Owner:** Docs Owner
- **Resolution steps:**
  1. Add prominent troubleshooting block for HF 404.
  2. Add local adapter fallback and mock backend quick checks.

## LOW

### 7) Python version friction (3.9 users fail install)
- **Description:** `pip install -e .` fails on Python 3.9 (correct by metadata, but common local setup issue).
- **Severity:** LOW
- **Effort estimate:** 20-40 minutes
- **Owner:** Docs Owner
- **Resolution steps:**
  1. Add preflight step: `python --version` must be >=3.10.
  2. Add pyenv/asdf snippet in install docs.

---

## Blocker Closure Criteria

A blocker is closed only when:
- It has reproducible proof in clean-checkout logs, and
- `release_readiness_report.md` can be rerun with no FAIL entries for that item.
