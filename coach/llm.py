"""Thin wrapper around the Anthropic Messages API.

Three jobs, nothing else: (1) disk-cache every response, (2) compute dollar
cost from usage, (3) keep a running spend ledger. Both implementations
(from-scratch and LangGraph) must go through the same model/prompt settings.
"""
import hashlib
import json
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()  # must run before get_client(): Langfuse reads its keys from the environment

from langfuse import get_client

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache" / "llm"
LEDGER = ROOT / "runs" / "spend.jsonl"

MODEL = "claude-haiku-5-5"

# $ per million tokens, prompts <= 100k tokens (verify on the pricing page;
# above 100k Haiku 5.5 is $0.50 / $2.50). Cache read/write prices not tracked yet.
PRICES = {"claude-haiku-5-5": (0.10, 0.50)}

_client = anthropic.Anthropic()
_lf = get_client()


def cost_usd(model: str, usage) -> float:
    p_in, p_out = PRICES[model]
    return (usage["input_tokens"] * p_in + usage["output_tokens"] * p_out) / 1e6


def call(messages, *, system=None, tools=None, model=MODEL, max_tokens=3000,
         effort="low", use_cache=True, name="llm-call") -> dict:
    """One Messages API call, traced as a Langfuse generation.
    Returns {content, stop_reason, usage, cost_usd, cached}."""
    params = dict(model=model, max_tokens=max_tokens, messages=messages,
                  output_config={"effort": effort})
    if system:
        params["system"] = system
    if tools:
        params["tools"] = tools

    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    path = CACHE_DIR / f"{key}.json"

    with _lf.start_as_current_observation(
            as_type="generation", name=name, model=model,
            input={"system": system, "messages": messages},
            model_parameters={"max_tokens": max_tokens, "effort": effort}) as gen:
        if use_cache and path.exists():
            out = {**json.loads(path.read_text()), "cached": True}
            real_cost = 0.0  # a cache hit costs nothing; keep the original cost in the result
        else:
            t0 = time.time()
            resp = _client.messages.create(**params)
            usage = {"input_tokens": resp.usage.input_tokens,
                     "output_tokens": resp.usage.output_tokens,
                     "cache_read_input_tokens": resp.usage.cache_read_input_tokens or 0,
                     "cache_creation_input_tokens": resp.usage.cache_creation_input_tokens or 0}
            out = {"content": [b.model_dump() for b in resp.content],
                   "stop_reason": resp.stop_reason, "usage": usage,
                   "cost_usd": cost_usd(model, usage), "latency_s": round(time.time() - t0, 2)}
            real_cost = out["cost_usd"]
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(out))
            LEDGER.parent.mkdir(parents=True, exist_ok=True)
            with LEDGER.open("a") as f:
                f.write(json.dumps({"ts": time.time(), "model": model, "key": key[:12], **usage,
                                    "cost_usd": real_cost}) + "\n")
            out["cached"] = False

        u = out["usage"]
        p_in, p_out = PRICES[model]
        gen.update(
            output=out["content"],
            metadata={"cached": out["cached"], "stop_reason": out["stop_reason"]},
            usage_details={"input": u["input_tokens"], "output": u["output_tokens"]},
            cost_details={"input": 0.0 if out["cached"] else u["input_tokens"] * p_in / 1e6,
                          "output": 0.0 if out["cached"] else u["output_tokens"] * p_out / 1e6})
    return out


def total_spend() -> float:
    if not LEDGER.exists():
        return 0.0
    return sum(json.loads(l)["cost_usd"] for l in LEDGER.read_text().splitlines())
