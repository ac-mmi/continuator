# Hugging Face Publish Guide — Continuator V10 LoRA

Publication target: `continuator-ai/continuator-v10-lora`  
Audit date: 2026-06-20  
Scope: exact commands for model publication and verification (no code changes)

---

## Pre-flight: artifact readiness

Before publishing, confirm local source artifacts:

| File | Status | Source path |
|------|--------|-------------|
| `adapter_config.json` | ✅ Present | `memory/archive/training-data/adapters_memory_v10_probe/adapter_config.json` |
| `adapters.safetensors` (ckpt 050) | ✅ Present | `memory/archive/training-data/adapters_memory_v10_probe/0000050_adapters.safetensors` |
| `README.md` model card | ❌ Missing (must draft) | — |
| `LICENSE` | ⚠️ Missing in adapter package | Use repo MIT (`continuator-release/LICENSE`) |

Important:
- Do **not** upload the ckpt symlink folder directly (`adapters_memory_v10_probe_ckpt_050/adapters.safetensors` is an absolute symlink).
- Upload concrete files into a clean staging directory.

Recommended weight file:
- Production runtime default is checkpoint **050** (`0000050_adapters.safetensors`, 20,126,646 bytes).

---

## 1) Create HF repo

```bash
# Authenticate once
huggingface-cli login

# Create model repo (skip if already exists)
huggingface-cli repo create continuator-ai/continuator-v10-lora --type model
```

If org/user namespace differs, update repo id consistently in:
- HF repo name
- `MEMORY_EXTRACTOR_HF_REPO` docs
- `continuator_engine/adapter_loader.py` default (`continuator-ai/continuator-v10-lora`)

---

## 2) Upload adapter files

### 2a) Build clean upload bundle

```bash
STAGE=/tmp/continuator-v10-lora-upload
SRC=/Users/acmmi/projects/memory/archive/training-data/adapters_memory_v10_probe

mkdir -p "$STAGE"

# Required runtime files
cp "$SRC/adapter_config.json" "$STAGE/adapter_config.json"
cp "$SRC/0000050_adapters.safetensors" "$STAGE/adapters.safetensors"

# Required model card + license
cp /Users/acmmi/projects/continuator-release/LICENSE "$STAGE/LICENSE"
# Create model card draft at $STAGE/README.md before upload
```

Model card minimum sections for `$STAGE/README.md`:
- Model id + base model (`Qwen/Qwen2.5-1.5B-Instruct`)
- Intended use (Continuator Continue/Explain extraction)
- Limitations (Apple Silicon MLX recommended; transformers optional)
- Files included (`adapter_config.json`, `adapters.safetensors`)
- Download + runtime usage commands
- License (MIT)

Optional but recommended: sanitize `adapter_config.json` training-only fields (`data`, `adapter_path`) before upload.

### 2b) Validate bundle locally

```bash
python3 - <<'PY'
from pathlib import Path
p = Path("/tmp/continuator-v10-lora-upload")
required = ["README.md", "LICENSE", "adapter_config.json", "adapters.safetensors"]
missing = [f for f in required if not (p / f).is_file()]
print("missing:", missing or "none")
if not missing:
    print("adapters bytes:", (p / "adapters.safetensors").stat().st_size)
PY
```

Expected adapter size: `20126646` bytes.

### 2c) Upload to Hugging Face

```bash
REPO=continuator-ai/continuator-v10-lora
STAGE=/tmp/continuator-v10-lora-upload

huggingface-cli upload "$REPO" "$STAGE/README.md" README.md
huggingface-cli upload "$REPO" "$STAGE/LICENSE" LICENSE
huggingface-cli upload "$REPO" "$STAGE/adapter_config.json" adapter_config.json
huggingface-cli upload "$REPO" "$STAGE/adapters.safetensors" adapters.safetensors
```

---

## 3) Verify public access

```bash
python3 - <<'PY'
from huggingface_hub import HfApi
repo = "continuator-ai/continuator-v10-lora"
info = HfApi().model_info(repo)
files = {s.rfilename for s in info.siblings}
for req in ["README.md", "LICENSE", "adapter_config.json", "adapters.safetensors"]:
    print(req, "OK" if req in files else "MISSING")
PY
```

Pass criteria: all four files report `OK`, no 404.

---

## 4) Verify anonymous download

Run in a shell **without** `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN`:

```bash
unset HF_TOKEN HUGGING_FACE_HUB_TOKEN
rm -rf /tmp/continuator-hf-anon
huggingface-cli download continuator-ai/continuator-v10-lora \
  --local-dir /tmp/continuator-hf-anon

ls -lh /tmp/continuator-hf-anon
test -f /tmp/continuator-hf-anon/adapter_config.json
test -f /tmp/continuator-hf-anon/adapters.safetensors
echo "anonymous download: OK"
```

Pass criteria: command exits 0 and both files exist.

---

## 5) Verify clean-machine inference

Use a fresh clone (no local adapter paths, no research repo):

```bash
# Clean clone
rm -rf /tmp/continuator-launch-audit
git clone /Users/acmmi/projects/continuator-release /tmp/continuator-launch-audit
cd /tmp/continuator-launch-audit
git checkout release/v0.1

# Python 3.10+ required
python3 --version
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -e ".[mlx]"

# Ensure no local override paths
unset MEMORY_EXTRACTOR_ADAPTER_PATH
export MEMORY_EXTRACTOR_HF_REPO=continuator-ai/continuator-v10-lora

# Run product commands
continuator --help
continuator continue examples/neck.txt --quiet
continuator explain examples/neck.txt --quiet
continuator continue examples/gitissue.txt --quiet
continuator continue examples/jquery.txt --quiet
continuator explain examples/gitissue.txt --quiet
continuator explain examples/jquery.txt --quiet
```

Pass criteria:
- All commands exit 0
- Continue output includes briefing sections (`## PROJECT`, `Next Action`)
- Explain output includes retrospective sections (`OVERVIEW`, `KEY TAKEAWAYS`)

---

## Publication gate

Mark HF publication complete only when all are true:

- [ ] Repo exists and is public
- [ ] Model card (`README.md`) uploaded
- [ ] License uploaded
- [ ] `adapter_config.json` uploaded
- [ ] `adapters.safetensors` uploaded (ckpt 050)
- [ ] Anonymous download verified
- [ ] Clean-machine continue/explain verified without local developer paths
