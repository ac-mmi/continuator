"""Convert MLX-LM LoRA adapters to Hugging Face PEFT layout for transformers backend."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_MLX_WEIGHT_NAMES = ("adapters.safetensors", "adapter_model.safetensors")
_PEFT_STAMP = ".peft_compat_v2"
_LAYER_RX = re.compile(r"\.layers\.(\d+)\.")


def is_mlx_adapter_config(config: dict[str, Any]) -> bool:
    """True when adapter_config.json is MLX training metadata, not PEFT."""
    if not config:
        return False
    if str(config.get("peft_type", "")).strip():
        return False
    return str(config.get("fine_tune_type", "")).strip().lower() == "lora" or bool(
        config.get("lora_parameters")
    )


def is_peft_adapter_config(config: dict[str, Any]) -> bool:
    return str(config.get("peft_type", "")).strip().upper() == "LORA"


def read_adapter_config(adapter_dir: Path) -> dict[str, Any]:
    path = adapter_dir / "adapter_config.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def mlx_weight_path(adapter_dir: Path) -> Path | None:
    for name in _MLX_WEIGHT_NAMES:
        candidate = adapter_dir / name
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    matches = sorted(adapter_dir.glob("*.safetensors"))
    return matches[0] if matches else None


def _layers_from_mlx_keys(keys: list[str]) -> list[int]:
    layers: set[int] = set()
    for key in keys:
        match = _LAYER_RX.search(key)
        if match:
            layers.add(int(match.group(1)))
    return sorted(layers)


def mlx_config_to_peft(mlx_config: dict[str, Any], *, layer_indices: list[int] | None = None) -> dict[str, Any]:
    lora = dict(mlx_config.get("lora_parameters") or {})
    rank = int(lora.get("rank") or mlx_config.get("r") or 8)
    alpha_raw = lora.get("scale", lora.get("lora_alpha", mlx_config.get("lora_alpha", rank)))
    # MLX-LM stores `scale` where PEFT expects `lora_alpha` ≈ scale * rank.
    alpha = int(float(alpha_raw) * rank) if "scale" in lora else int(float(alpha_raw))
    dropout = float(lora.get("dropout", lora.get("lora_dropout", 0.0)))
    base_model = str(
        mlx_config.get("model")
        or mlx_config.get("base_model_name_or_path")
        or "Qwen/Qwen2.5-1.5B-Instruct"
    ).strip()

    peft_cfg: dict[str, Any] = {
        "peft_type": "LORA",
        "task_type": "CAUSAL_LM",
        "r": rank,
        "lora_alpha": alpha,
        "lora_dropout": dropout,
        "target_modules": [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        "base_model_name_or_path": base_model,
        "bias": "none",
        "inference_mode": True,
    }
    if layer_indices:
        peft_cfg["layers_to_transform"] = list(layer_indices)
    return peft_cfg


def _remap_mlx_weight_key(key: str) -> str | None:
    if key.endswith(".lora_a"):
        return key.replace("model.", "base_model.model.model.").replace(
            ".lora_a", ".lora_A.default.weight"
        )
    if key.endswith(".lora_b"):
        return key.replace("model.", "base_model.model.model.").replace(
            ".lora_b", ".lora_B.default.weight"
        )
    return None


def convert_mlx_adapter_to_peft(
    adapter_dir: Path,
    output_dir: Path,
    *,
    force: bool = False,
) -> Path:
    """Write PEFT adapter_config.json + adapter_model.safetensors from MLX layout."""
    adapter_dir = adapter_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    peft_config_path = output_dir / "adapter_config.json"
    peft_weights_path = output_dir / "adapter_model.safetensors"
    if not force and peft_config_path.is_file() and peft_weights_path.is_file():
        cfg = read_adapter_config(output_dir)
        if is_peft_adapter_config(cfg):
            return output_dir

    mlx_config = read_adapter_config(adapter_dir)
    if not is_mlx_adapter_config(mlx_config):
        raise ValueError(f"adapter at {adapter_dir} is not MLX LoRA metadata")

    src_weights = mlx_weight_path(adapter_dir)
    if src_weights is None:
        raise FileNotFoundError(f"no LoRA safetensors found under {adapter_dir}")

    try:
        from safetensors import safe_open
        from safetensors.torch import save_file
    except ImportError as exc:
        raise RuntimeError("safetensors is required to convert MLX LoRA adapters") from exc

    import torch

    state: dict[str, torch.Tensor] = {}
    mlx_keys: list[str] = []
    with safe_open(str(src_weights), framework="pt") as reader:
        mlx_keys = list(reader.keys())
        for key in mlx_keys:
            mapped = _remap_mlx_weight_key(key)
            if not mapped:
                continue
            tensor = reader.get_tensor(key)
            # MLX lora_a/lora_b layouts differ from PEFT; both need transpose.
            state[mapped] = tensor.T.contiguous()

    if not state:
        raise ValueError(f"no convertible MLX LoRA tensors in {src_weights}")

    layer_indices = _layers_from_mlx_keys(mlx_keys)
    peft_cfg = mlx_config_to_peft(mlx_config, layer_indices=layer_indices or None)
    peft_config_path.write_text(json.dumps(peft_cfg, indent=2) + "\n", encoding="utf-8")
    save_file(state, str(peft_weights_path))
    return output_dir


def peft_compat_cache_dir(adapter_dir: Path) -> Path:
    return adapter_dir / _PEFT_STAMP


def load_transformers_peft_model(base_model: str, adapter_dir: Path):
    """Load base causal LM + MLX-converted (or native) PEFT LoRA for inference."""
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    adapter_dir = adapter_dir.expanduser().resolve()
    cfg = read_adapter_config(adapter_dir)
    if not is_peft_adapter_config(cfg):
        raise ValueError(f"PEFT adapter config missing at {adapter_dir}")

    weights_path = adapter_dir / "adapter_model.safetensors"
    if not weights_path.is_file():
        raise FileNotFoundError(f"PEFT adapter weights missing: {weights_path}")

    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        trust_remote_code=True,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    )
    lora_cfg = LoraConfig(
        r=int(cfg.get("r") or 8),
        lora_alpha=int(cfg.get("lora_alpha") or 16),
        lora_dropout=float(cfg.get("lora_dropout") or 0.0),
        target_modules=list(cfg.get("target_modules") or []),
        layers_to_transform=list(cfg.get("layers_to_transform") or []) or None,
        bias=str(cfg.get("bias") or "none"),
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_cfg)

    from safetensors.torch import load_file

    state = load_file(str(weights_path))
    model.load_state_dict(state, strict=False)
    model.eval()
    return model, tokenizer


def resolve_peft_adapter_dir(adapter_dir: Path, *, force_rebuild: bool = False) -> Path:
    """Return a PEFT-loadable adapter directory (original or converted cache)."""
    adapter_dir = adapter_dir.expanduser().resolve()
    config = read_adapter_config(adapter_dir)
    if is_peft_adapter_config(config):
        weights = adapter_dir / "adapter_model.safetensors"
        if weights.is_file():
            return adapter_dir

    if not is_mlx_adapter_config(config):
        return adapter_dir

    cache_dir = peft_compat_cache_dir(adapter_dir)
    if not force_rebuild:
        cached_cfg = read_adapter_config(cache_dir)
        src_mtime = mlx_weight_path(adapter_dir)
        src_ts = src_mtime.stat().st_mtime if src_mtime else 0.0
        cache_ts = min(
            (cache_dir / "adapter_config.json").stat().st_mtime,
            (cache_dir / "adapter_model.safetensors").stat().st_mtime,
        ) if (cache_dir / "adapter_model.safetensors").is_file() else 0.0
        if is_peft_adapter_config(cached_cfg) and cache_ts >= src_ts:
            return cache_dir

    return convert_mlx_adapter_to_peft(adapter_dir, cache_dir, force=True)
