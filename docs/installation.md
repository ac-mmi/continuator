# Installation

## Requirements

- Python 3.10 or newer
- macOS with Apple Silicon for default MLX backend (recommended)
- Linux/Windows: use `transformers` backend or `mock` for smoke tests

## Standard install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## With development tools

```bash
pip install -e ".[dev]"
```

## MLX backend (Apple Silicon)

```bash
pip install -e ".[mlx]"
export MEMORY_EXTRACTOR_BACKEND=mlx
```

## Transformers backend (cross-platform)

```bash
pip install -e ".[transformers]"
export MEMORY_EXTRACTOR_BACKEND=transformers
```

## Model weights

On first extraction run, Continuator downloads the V10 LoRA adapter from Hugging Face into `~/.cache/continuator/models/v10/`.

Pre-download:

```bash
pip install huggingface_hub
hf download ac-mmi/continuator-v10-lora \
  --local-dir ~/.cache/continuator/models/v10
```

Use a local path:

```bash
export MEMORY_EXTRACTOR_ADAPTER_PATH=~/.cache/continuator/models/v10
```

## Verify

```bash
# Structural smoke test (no model)
MEMORY_EXTRACTOR_BACKEND=mock continuator continue examples/neck.txt --quiet

# Full pipeline (requires adapter + MLX on macOS)
continuator continue examples/neck.txt
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Repository Not Found` on HF download | Model repo not published yet — use `MEMORY_EXTRACTOR_ADAPTER_PATH` or `mock` backend |
| MLX import error | `pip install -e ".[mlx]"` |
| `sentence_transformers` download slow | First run downloads MiniLM embedder for chunk ranking — one-time |
| Empty briefing | Check `--verbose` for extraction errors |

See [`.env.example`](../.env.example) for all environment variables.
