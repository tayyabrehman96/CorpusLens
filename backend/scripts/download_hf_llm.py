"""
Pre-download a Hugging Face model into backend/data/hf_hub (for offline / air-gapped use later).

Usage (from repo root or backend):
  .\\.venv\\Scripts\\python.exe scripts\\download_hf_llm.py --model Qwen/Qwen2.5-0.5B-Instruct
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--model",
        default="Qwen/Qwen2.5-0.5B-Instruct",
        help="Hugging Face model repo id",
    )
    args = p.parse_args()

    here = Path(__file__).resolve().parent
    data = (here.parent / "data").resolve()
    hub = data / "hf_hub"
    hub.mkdir(parents=True, exist_ok=True)
    cache = str(hub)
    os.environ["HF_HOME"] = cache
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(hub / "hub")

    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"Downloading {args.model} into {cache} ...")
    AutoTokenizer.from_pretrained(args.model, cache_dir=cache)
    AutoModelForCausalLM.from_pretrained(
        args.model,
        cache_dir=cache,
    )
    print("Done.")


if __name__ == "__main__":
    main()
