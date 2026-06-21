# Validation runs (generated)

Output directory for `scripts/validation_runner_v1.py`.

Each session gets a subdirectory with checkpoint, resume briefing, LLM prompts, and metadata.

**Do not commit large validation runs** — add session folders to `.gitignore` if needed.

```bash
python scripts/validation_runner_v1.py examples/ -o validation_runs
```

See `resume_test_pack.md` for the full workflow.
