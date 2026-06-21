#!/usr/bin/env python3
"""Convert MLX-LM V10 LoRA on disk to Hugging Face PEFT files for HF Hub upload.

The public repo ac-mmi/continuator-v10-lora ships MLX layout (adapter_config.json +
adapters.safetensors). Windows/Linux use transformers+PEFT. Continuator auto-converts
on first transformers load, but you can also publish PEFT files alongside MLX files:

  python scripts/convert_mlx_lora_to_peft.py \\
    --input ~/.cache/continuator/models/v10 \\
    --output ./peft_upload/v10

Then upload adapter_config.json + adapter_model.safetensors to Hugging Face
(keep existing adapters.safetensors for Mac MLX users).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "continuator_engine"))

from adapter_peft_compat import convert_mlx_adapter_to_peft, read_adapter_config, is_mlx_adapter_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert MLX LoRA adapter to PEFT layout")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path.home() / ".cache" / "continuator" / "models" / "v10",
        help="MLX adapter directory (adapter_config.json + adapters.safetensors)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directory to write PEFT adapter_config.json + adapter_model.safetensors",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite output directory")
    args = parser.parse_args()

    src = args.input.expanduser().resolve()
    if not src.is_dir():
        print(f"error: input directory not found: {src}", file=sys.stderr)
        return 2

    cfg = read_adapter_config(src)
    if not is_mlx_adapter_config(cfg):
        print(
            "error: input does not look like MLX LoRA metadata "
            "(expected fine_tune_type=lora without peft_type)",
            file=sys.stderr,
        )
        return 2

    out = convert_mlx_adapter_to_peft(src, args.output.expanduser().resolve(), force=args.force)
    print(f"Wrote PEFT adapter to {out}")
    print("Upload to Hugging Face:")
    print(f"  {out / 'adapter_config.json'}")
    print(f"  {out / 'adapter_model.safetensors'}")
    print("Keep existing adapters.safetensors for Apple Silicon (mlx) users.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
