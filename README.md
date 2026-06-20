# Continuator

**Turn a long conversation into a continuation briefing for another AI.**

Continuator reads a long ChatGPT, Claude, or tutoring thread and produces a structured handoff briefing — project objective, current position, completed work, active problems, and next action — so you can paste context into a fresh chat and continue naturally.

## Screenshots

**Welcome screen** — launch the TUI with `continuator`:

![Continuator welcome screen](docs/images/tui-welcome.png)

**Explain view** — retrospective summary of a long conversation:

![Continuator explain view](docs/images/tui-explain.png)

```bash
pip install -e .
continuator continue examples/neck.txt
```

## Features

- **Continue** — structured continuation briefing for AI handoff
- **Explain** — retrospective conversation summary
- **Export** — platform-ready paste blocks (Claude, ChatGPT, Gemini)
- **Inspect** — chunking and ranker audit without full extraction
- **TUI** — interactive terminal UI (default when no subcommand is given)

## Install

Requires **Python 3.10+**. Works on **macOS, Windows, and Linux**.

```bash
git clone https://github.com/continuator-ai/continuator.git
cd continuator
git checkout release/v0.1

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

### Platform-specific extras

| Platform | Install | Backend (auto) |
|----------|---------|----------------|
| **macOS Apple Silicon** | `pip install -e ".[mlx]"` | `mlx` (fast, recommended) |
| **Windows / Linux / Intel Mac** | `pip install -e ".[transformers]"` | `transformers` |

Continuator picks the backend automatically. Override with `MEMORY_EXTRACTOR_BACKEND` if needed.

### Model weights

Continuator downloads the V10 LoRA adapter from Hugging Face on first run:

```bash
# Optional: pre-download
hf download ac-mmi/continuator-v10-lora \
  --local-dir ~/.cache/continuator/models/v10
export MEMORY_EXTRACTOR_ADAPTER_PATH=~/.cache/continuator/models/v10
```

Or point to a local adapter directory:

```bash
export MEMORY_EXTRACTOR_ADAPTER_PATH=/path/to/adapter
```

See [`.env.example`](.env.example) for all configuration options.

### Smoke test (no model)

```bash
MEMORY_EXTRACTOR_BACKEND=mock continuator continue examples/neck.txt --quiet
```

## Quick start

```bash
# Continuation briefing
continuator continue examples/neck.txt

# Explain mode
continuator explain examples/neck.txt

# Export for Claude
continuator export examples/neck.txt --for claude

# Interactive TUI
continuator
```

## Examples

Sample conversations live in [`examples/`](examples/):

| File | Description |
|------|-------------|
| `neck.txt` | Short posture/health tutoring thread |
| `gitissue.txt` | GitHub issue discussion |
| `jquery.txt` | jQuery learning conversation |

## Commands

| Command | Description |
|---------|-------------|
| `continuator continue FILE` | Generate continuation briefing |
| `continuator explain FILE` | Generate retrospective summary |
| `continuator export FILE --for claude` | Platform export |
| `continuator inspect FILE` | Chunk/ranker audit |
| `continuator benchmark DIR` | Batch evaluation |

Full CLI reference: [docs/cli-ux-examples.md](docs/cli-ux-examples.md)

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `MEMORY_EXTRACTOR_BACKEND` | auto: `mlx` (Apple Silicon) or `transformers` (elsewhere) | `mlx`, `transformers`, or `mock` |
| `MEMORY_MODEL` | `v10` | Extraction schema version |
| `MEMORY_EXTRACTOR_HF_REPO` | `ac-mmi/continuator-v10-lora` | Hugging Face adapter repo |
| `MEMORY_EXTRACTOR_ADAPTER_PATH` | — | Local adapter directory (skips download) |
| `CONTINUATOR_MODEL_CACHE` | `~/.cache/continuator/models` | Download cache |
| `HF_TOKEN` | — | Hugging Face token for private repos |

## Development

```bash
pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Architecture

```
continuator/           CLI + TUI (this package)
continuator_engine/    V10 extraction + briefing pipeline
examples/              Sample conversations
tests/                 Unit tests
docs/                  Documentation
```

The extraction pipeline uses a fine-tuned LoRA on Qwen2.5-1.5B-Instruct. Weights are fetched from Hugging Face — not bundled in Git.

## License

MIT — see [LICENSE](LICENSE).
