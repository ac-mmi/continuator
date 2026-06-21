# Installation

## Requirements

- Python 3.10 or newer
- macOS, Windows, or Linux

## Standard install

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows PowerShell

pip install -e .
```

## Platform-specific backends

Continuator auto-selects the extraction backend:

| Platform | Default backend | Install extra |
|----------|-----------------|---------------|
| macOS Apple Silicon | `mlx` | `pip install -e ".[mlx]"` |
| Windows | `transformers` | `pip install -e ".[transformers]"` |
| Linux | `transformers` | `pip install -e ".[transformers]"` |
| Intel Mac | `transformers` | `pip install -e ".[transformers]"` |

Override anytime:

```bash
export MEMORY_EXTRACTOR_BACKEND=transformers   # Windows PowerShell: $env:MEMORY_EXTRACTOR_BACKEND="transformers"
```

## With development tools

```bash
pip install -e ".[dev]"
```

## MLX backend (Apple Silicon Mac)

```bash
pip install -e ".[mlx]"
```

Backend is set to `mlx` automatically on Apple Silicon.

## Transformers backend (Windows / Linux / Intel Mac)

```bash
pip install -e ".[transformers]"
```

Backend is set to `transformers` automatically on non-Apple-Silicon platforms.

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
# Structural smoke test (no model, all platforms)
MEMORY_EXTRACTOR_BACKEND=mock continuator continue examples/neck.txt --quiet

# Full pipeline (requires platform extra: [mlx] or [transformers])
continuator continue examples/neck.txt
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Repository Not Found` on HF download | Check https://huggingface.co/ac-mmi/continuator-v10-lora is public |
| MLX import error on Mac | `pip install -e ".[mlx]"` (Apple Silicon only) |
| Transformers/torch error on Windows/Linux | `pip install -e ".[transformers]"` |
| Wrong backend on Intel Mac | Should auto-use `transformers`; set `MEMORY_EXTRACTOR_BACKEND=transformers` |
| `sentence_transformers` download slow | First run downloads MiniLM embedder — one-time |
| Empty briefing | Run with `--verbose` for extraction errors |

See [`.env.example`](../.env.example) for all environment variables.
