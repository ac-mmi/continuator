# Public Beta Launch

**Date:** 2026-06-20  
**Version:** v0.1.0  
**Status:** READY FOR PUBLIC BETA

---

## Model (Hugging Face)

**Published:** https://huggingface.co/ac-mmi/continuator-v10-lora

Files on Hub:
- `README.md` (model card)
- `LICENSE`
- `adapter_config.json`
- `adapters.safetensors` (~20 MB, checkpoint 050)

Anonymous download verified (no token required).

---

## GitHub publish steps

```bash
cd /Users/acmmi/projects/continuator-release

# Review changes
git status
git diff

# Commit release prep
git add -A
git commit -m "Point default HF model to ac-mmi/continuator-v10-lora for v0.1 beta"

# Create GitHub repo (via web or gh), then:
git remote add origin https://github.com/YOUR_USER/continuator.git
git push -u origin release/v0.1

# Tag release
git tag v0.1.0
git push origin v0.1.0
```

Create GitHub Release from tag `v0.1.0` (see release notes below).

---

## HF publish steps (completed)

Already done:

```bash
hf upload ac-mmi/continuator-v10-lora /tmp/continuator-v10-lora-upload . --repo-type model
```

Repo is **public**. Verify anytime:

```bash
unset HF_TOKEN HUGGING_FACE_HUB_TOKEN
hf download ac-mmi/continuator-v10-lora --local-dir /tmp/hf-test
```

---

## Release tag

**Tag:** `v0.1.0`  
**Branch:** `release/v0.1`

---

## First release notes (copy for GitHub Release)

### Continuator v0.1.0 — Public Beta

Turn a long conversation into a continuation briefing for another AI.

**What's included**
- CLI: `continue`, `explain`, `export`, `inspect`, `benchmark`
- Textual TUI (default: run `continuator` with no subcommand)
- V10 LoRA extraction via Hugging Face

**Install**

```bash
git clone https://github.com/YOUR_USER/continuator.git
cd continuator
git checkout release/v0.1
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[mlx]"
```

Requires Python 3.10+ and Apple Silicon for default MLX backend.

**Model**

Downloaded automatically on first run from:
https://huggingface.co/ac-mmi/continuator-v10-lora

**Quick start**

```bash
continuator continue examples/neck.txt
continuator explain examples/neck.txt
```

**Smoke test (no model download)**

```bash
MEMORY_EXTRACTOR_BACKEND=mock continuator continue examples/neck.txt --quiet
```

---

## Post-beta (optional before full public release)

- [ ] Add `docs/cli-reference.md`
- [ ] Add `docs/environment.md`
- [ ] Add `docs/architecture.md`
- [ ] GitHub Actions CI with mock backend
- [ ] PyPI publish (`pip install continuator`)

---

## Verification checklist (passed)

- [x] HF repo public
- [x] Anonymous download works
- [x] `continuator continue examples/neck.txt` works (default HF repo)
- [x] `continuator explain examples/neck.txt` works (default HF repo)
- [x] Default repo id updated to `ac-mmi/continuator-v10-lora`
- [x] `models/README.md` added
