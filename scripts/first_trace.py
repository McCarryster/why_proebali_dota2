import sys
import uuid
from pathlib import Path

from langfuse import get_client, propagate_attributes

from coach import llm
from coach.dota import opendota
from coach.dota.digest import digest

MATCH_ID = 9041878637  # a comeback from data/matches.json
lf = get_client()
print("langfuse auth ok:", lf.auth_check())

run_id = uuid.uuid4().hex[:8]
with lf.start_as_current_observation(as_type="span", name="first-trace") as root:
    with propagate_attributes(trace_name="first-trace",
                              metadata={"system": "smoke-test", "match_id": str(MATCH_ID), "run_id": run_id}):
        text = digest(opendota.get_match(MATCH_ID))
        q = "In two sentences: who won, and around which minute did the gold lead flip?"
        r = llm.call([{"role": "user", "content": f"{text}\n\nQuestion: {q}"}],
                     name="smoke-test-answer", max_tokens=400)
        root.update(input=q, output=r["content"][-1].get("text"))
        print(r["content"][-1].get("text"))
        print(r["usage"], f"${r['cost_usd']:.6f}", "cached=", r["cached"])
        print("trace:", lf.get_trace_url())
lf.flush()
