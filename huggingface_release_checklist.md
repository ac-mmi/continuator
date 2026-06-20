# Hugging Face Release Checklist (V10 LoRA)

Scope: verify and publish the model package expected by the release runtime (`continuator-ai/continuator-v10-lora`).

## Current local artifact audit

Source inspected locally:
- `/Users/acmmi/projects/memory/archive/training-data/adapters_memory_v10_probe_ckpt_050/`
- `/Users/acmmi/projects/memory/archive/training-data/adapters_memory_v10_probe/`

Findings:
- `adapter_config.json`: **present**
- `adapters.safetensors`: **present** (symlink in ckpt folder, concrete file in source folder)
- README model card: **missing in local artifact package**

Technical notes:
- Current ckpt folder uses absolute symlink for `adapters.safetensors`.
- For HF upload, use concrete files (no absolute symlinks).

---

## Required files in HF repo

Minimum required payload in `continuator-ai/continuator-v10-lora`:

1. `README.md` (model card)
2. `adapter_config.json`
3. `adapters.safetensors`

Recommended additional files:
- `LICENSE` (or model card license section)
- `SHA256SUMS` for artifact integrity
- `CHANGELOG.md` (optional)

---

## Model card checklist (`README.md` on HF)

Include:
- Model name/version: `continuator-v10-lora`
- Base model: `Qwen/Qwen2.5-1.5B-Instruct`
- Intended use: Continuator extraction for Continue/Explain pipelines
- Out-of-scope use and limitations
- Inference requirements (`mlx`/`transformers`)
- Exact local loading instructions with `MEMORY_EXTRACTOR_ADAPTER_PATH`
- Example command:
  - `continuator continue examples/neck.txt`
- Privacy and safety notes
- License and attribution

---

## Exact upload steps

## 1) Prepare a clean upload folder

```bash
mkdir -p /tmp/continuator-v10-lora-upload
cp /Users/acmmi/projects/memory/archive/training-data/adapters_memory_v10_probe/adapter_config.json \
  /tmp/continuator-v10-lora-upload/
cp /Users/acmmi/projects/memory/archive/training-data/adapters_memory_v10_probe/adapters.safetensors \
  /tmp/continuator-v10-lora-upload/
# add README.md model card
```

## 2) Validate files before upload

```bash
ls -lh /tmp/continuator-v10-lora-upload
python - <<'PY'
from pathlib import Path
p=Path('/tmp/continuator-v10-lora-upload')
assert (p/'adapter_config.json').is_file()
assert (p/'adapters.safetensors').is_file()
assert (p/'README.md').is_file()
print('package ok')
PY
```

## 3) Login and create repo

```bash
huggingface-cli login
huggingface-cli repo create continuator-ai/continuator-v10-lora --type model
```

If repo exists, skip create.

## 4) Upload artifacts

```bash
huggingface-cli upload continuator-ai/continuator-v10-lora /tmp/continuator-v10-lora-upload/README.md README.md
huggingface-cli upload continuator-ai/continuator-v10-lora /tmp/continuator-v10-lora-upload/adapter_config.json adapter_config.json
huggingface-cli upload continuator-ai/continuator-v10-lora /tmp/continuator-v10-lora-upload/adapters.safetensors adapters.safetensors
```

## 5) Verify from clean environment

```bash
python - <<'PY'
from huggingface_hub import HfApi
repo='continuator-ai/continuator-v10-lora'
info=HfApi().model_info(repo)
names={s.rfilename for s in info.siblings}
for req in ['README.md','adapter_config.json','adapters.safetensors']:
    print(req, 'OK' if req in names else 'MISSING')
PY
```

## 6) End-to-end runtime verification

```bash
# clean clone
pip install -e .
huggingface-cli download continuator-ai/continuator-v10-lora --local-dir ~/.cache/continuator/models/v10
export MEMORY_EXTRACTOR_ADAPTER_PATH=~/.cache/continuator/models/v10
continuator continue examples/neck.txt --quiet
continuator explain examples/neck.txt --quiet
```

Success criteria: both commands exit 0 with generated content.

---

## Release gate (HF)

Mark HF ready only when all are true:
- [ ] Public model repo reachable anonymously (no 404)
- [ ] `README.md` model card present
- [ ] `adapter_config.json` present
- [ ] `adapters.safetensors` present
- [ ] Clean-machine download works
- [ ] Continuator continue/explain work without local developer paths
