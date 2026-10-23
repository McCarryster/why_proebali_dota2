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