import sys
from pathlib import Path

from coach import llm

r = llm.call([{"role": "user", "content": "In one sentence: what is a 'lane' in Dota 2?"}],
             max_tokens=300)
for b in r["content"]:
    print(f"[{b['type']}]", b.get("text") or b.get("thinking") or "")
print("stop_reason:", r["stop_reason"])
print("usage:", r["usage"])
print(f"cost: ${r['cost_usd']:.6f}  cached={r['cached']}  total spend: ${llm.total_spend():.6f}")
