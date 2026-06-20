# Contributing to Continuator

Thank you for your interest in contributing. This repository is the **public release** of Continuator — a focused CLI product. Keep changes scoped to the product surface.

## Getting started

```bash
git clone https://github.com/continuator-ai/continuator.git
cd continuator
git checkout release/v0.1
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Project layout

| Path | Purpose |
|------|---------|
| `continuator/` | CLI, TUI, commands |
| `continuator_engine/` | Extraction and briefing runtime |
| `tests/` | Unit tests |
| `examples/` | Sample conversations |
| `docs/` | User and developer docs |

## What belongs here

- CLI/TUI improvements
- Export formatting (Continue, Explain modes)
- Documentation and examples
- Tests for product behavior
- Hugging Face adapter loading improvements

## What does not belong here

- Training scripts, datasets, or LoRA checkpoints
- Research benchmarks and audit report generators
- Legacy IDE/web UI code
- Personal conversation transcripts

Those live in the private research repository and Hugging Face model repos.

## Running tests

```bash
# Fast — no model required
pytest

# Smoke test with mock backend
MEMORY_EXTRACTOR_BACKEND=mock continuator continue examples/neck.txt --quiet
```

## Pull requests

1. Fork and branch from `release/v0.1` (or `main` after release)
2. Keep diffs focused — one concern per PR
3. Add or update tests for behavior changes
4. Run `pytest` before submitting
5. Do not commit `.env`, model weights, or personal transcripts

## Code style

- Match existing naming and import style in the file you edit
- Prefer extending existing functions over new abstractions
- Comments only for non-obvious logic

## Reporting issues

Include:

- Python version and OS
- `continuator continue --help` output
- Whether you use `mlx`, `transformers`, or `mock` backend
- Minimal conversation sample that reproduces the issue (sanitized — no real PII)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
