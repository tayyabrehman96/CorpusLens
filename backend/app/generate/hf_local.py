"""
Local Hugging Face causal LM: weights download into backend/data/hf_hub (no Ollama).
CPU-friendly defaults; first run downloads the model once (needs internet unless cache is pre-seeded).
"""

from __future__ import annotations

import asyncio
import os
import queue
from pathlib import Path
from threading import Thread
from typing import Any, AsyncIterator, Optional

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

from app.config import Settings

_bundle: Optional[tuple[Any, Any]] = None


def _hf_hub_root(settings: Settings) -> str:
    root = settings.data_dir / "hf_hub"
    root.mkdir(parents=True, exist_ok=True)
    return str(root.resolve())


def _load_model(settings: Settings) -> tuple[AutoModelForCausalLM, AutoTokenizer]:
    global _bundle
    if _bundle is not None:
        return _bundle

    cache = _hf_hub_root(settings)
    os.environ.setdefault("HF_HOME", cache)
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", os.path.join(cache, "hub"))

    model_ref = settings.hf_local_model.strip()
    mp = Path(model_ref)
    if mp.is_dir() and (mp / "config.json").exists():
        model_ref = str(mp.resolve())

    dtype = torch.float32
    tokenizer = AutoTokenizer.from_pretrained(
        model_ref,
        cache_dir=cache,
        trust_remote_code=settings.hf_trust_remote_code,
    )
    if tokenizer.pad_token is None and tokenizer.eos_token is not None:
        tokenizer.pad_token = tokenizer.eos_token
    # No device_map / low_cpu_mem_usage — those require the optional `accelerate` package on many setups.
    model = AutoModelForCausalLM.from_pretrained(
        model_ref,
        cache_dir=cache,
        torch_dtype=dtype,
        trust_remote_code=settings.hf_trust_remote_code,
    )
    model.eval()
    _bundle = (model, tokenizer)
    return _bundle


def _messages_to_token_ids(
    model: Any,
    tokenizer: Any,
    messages: list[dict[str, str]],
    settings: Settings,
) -> Any:
    try:
        if getattr(tokenizer, "chat_template", None) is not None:
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            raise ValueError("no chat template")
    except (TypeError, ValueError, AttributeError):
        parts = []
        for m in messages:
            parts.append(f"{m.get('role', 'user').upper()}: {m.get('content', '')}")
        text = "\n\n".join(parts) + "\n\nASSISTANT:"

    model_max = int(getattr(model.config, "max_position_embeddings", 8192) or 8192)
    budget = min(model_max, settings.hf_context_tokens) - settings.hf_max_new_tokens - 32
    max_length = max(256, budget)

    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=max_length,
    )
    return inputs.to(model.device)


def _sync_stream_tokens(settings: Settings, messages: list[dict[str, str]]):
    model, tokenizer = _load_model(settings)
    inputs = _messages_to_token_ids(model, tokenizer, messages, settings)
    streamer = TextIteratorStreamer(
        tokenizer,
        skip_prompt=True,
        skip_special_tokens=True,
    )
    gen_kwargs = {
        **inputs,
        "streamer": streamer,
        "max_new_tokens": settings.hf_max_new_tokens,
        "do_sample": settings.hf_do_sample,
        "temperature": settings.hf_temperature,
        "top_p": settings.hf_top_p,
    }

    def _run() -> None:
        with torch.inference_mode():
            model.generate(**gen_kwargs)

    thread = Thread(target=_run, daemon=True)
    thread.start()
    for text in streamer:
        if text:
            yield text
    thread.join(timeout=600)


async def stream_hf_local(
    settings: Settings,
    messages: list[dict[str, str]],
) -> AsyncIterator[str]:
    """
    Bridge sync HF streaming to asyncio without run_coroutine_threadsafe (avoids stalls/deadlocks).
    """
    q: queue.Queue = queue.Queue()
    err: list[BaseException] = []

    def producer() -> None:
        try:
            for piece in _sync_stream_tokens(settings, messages):
                q.put(piece)
        except BaseException as e:
            err.append(e)
        finally:
            q.put(None)

    Thread(target=producer, daemon=True).start()
    while True:
        item = await asyncio.to_thread(q.get)
        if item is None:
            break
        yield str(item)
    if err:
        raise err[0]
