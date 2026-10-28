class FakeLLM:
    """Replays scripted replies and records every call it receives."""
    def __init__(self, replies: list):
        self.replies = list(replies)       # copy, so the test's own list is not modified
        self.calls = []                    # what the loop sent us, in order

    def __call__(self, messages: list[dict], **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if not self.replies:
            raise AssertionError("FakeLLM ran out of scripted replies")
        return self.replies.pop(0)


class RoutedFakeLLM:
    """Like FakeLLM, but replies are chosen by WHICH hypothesis is asking, not by call order."""
    def __init__(self, replies_by_hypothesis: dict[str, list]):
        self.replies = {k: list(v) for k, v in replies_by_hypothesis.items()}
        self.calls = []

    def __call__(self, messages: list[dict], **kwargs):
        key = next((k for k in self.replies if k in kwargs["system"]), None)
        if key is None:
            raise AssertionError(f"RoutedFakeLLM: no route for system text starting: {kwargs['system'][:100]}")
        self.calls.append({"messages": messages, "key": key, **kwargs})
        if not self.replies[key]:
            raise AssertionError(f"RoutedFakeLLM ran out of replies for: {key}")
        return self.replies[key].pop(0)


def tool_use(name: str, input: dict, id: str = "toolu_1") -> dict:
    return {"type": "tool_use", "id": id, "name": name, "input": input}

def reply(*blocks, stop_reason: str = "tool_use") -> dict:
    return {
        "content": list(blocks),
        "stop_reason": stop_reason,
        "usage": {"input_tokens": 100, "output_tokens": 50,
                  "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        "cost_usd": 0.0,
        "cached": False,
    }