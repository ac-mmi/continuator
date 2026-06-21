"""MLX → PEFT adapter conversion for transformers backend."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapter_peft_compat import (
    convert_mlx_adapter_to_peft,
    is_mlx_adapter_config,
    is_peft_adapter_config,
    mlx_config_to_peft,
    read_adapter_config,
    resolve_peft_adapter_dir,
)


def test_is_mlx_adapter_config():
    assert is_mlx_adapter_config({"fine_tune_type": "lora", "lora_parameters": {"rank": 8}})
    assert not is_mlx_adapter_config({"peft_type": "LORA", "r": 8})


def test_mlx_config_to_peft_mapping():
    cfg = mlx_config_to_peft(
        {
            "model": "Qwen/Qwen2.5-1.5B-Instruct",
            "lora_parameters": {"rank": 8, "scale": 20.0, "dropout": 0.0},
        },
        layer_indices=[12, 13],
    )
    assert cfg["peft_type"] == "LORA"
    assert cfg["r"] == 8
    assert cfg["lora_alpha"] == 20
    assert cfg["layers_to_transform"] == [12, 13]


def test_convert_mlx_adapter_roundtrip(tmp_path: Path):
    try:
        from safetensors.torch import save_file
        import torch
    except ImportError:
        pytest.skip("safetensors/torch not installed")

    mlx_dir = tmp_path / "mlx"
    mlx_dir.mkdir()
    mlx_cfg = {
        "fine_tune_type": "lora",
        "model": "Qwen/Qwen2.5-1.5B-Instruct",
        "lora_parameters": {"rank": 2, "scale": 4.0, "dropout": 0.0},
    }
    (mlx_dir / "adapter_config.json").write_text(json.dumps(mlx_cfg), encoding="utf-8")
    save_file(
        {
            "model.layers.1.self_attn.q_proj.lora_a": torch.randn(4, 2),
            "model.layers.1.self_attn.q_proj.lora_b": torch.randn(2, 4),
        },
        str(mlx_dir / "adapters.safetensors"),
    )

    out = convert_mlx_adapter_to_peft(mlx_dir, tmp_path / "peft")
    peft_cfg = read_adapter_config(out)
    assert is_peft_adapter_config(peft_cfg)
    assert (out / "adapter_model.safetensors").is_file()

    resolved = resolve_peft_adapter_dir(mlx_dir)
    assert resolved == mlx_dir / ".peft_compat"
    assert is_peft_adapter_config(read_adapter_config(resolved))
