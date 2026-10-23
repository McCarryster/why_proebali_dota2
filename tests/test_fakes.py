import pytest

from tests.fakes import FakeLLM, reply, tool_use


def test_replies_come_out_in_order_and_calls_are_recorded():
    first = reply(tool_use("fetch_match", {"match_id": 1}))
    second = reply(tool_use("submit_finding", {"claim": "x"}))
    llm = FakeLLM([first, second])                 # an INSTANCE: note the parentheses and the list

    assert llm([{"role": "user", "content": "hi"}], system="s") is first
    assert llm([{"role": "user", "content": "again"}], system="s") is second

    assert len(llm.calls) == 2
    assert llm.calls[0]["system"] == "s"           # kwargs were recorded too


def test_running_out_of_replies_fails_loudly():
    llm = FakeLLM([reply(tool_use("fetch_match", {"match_id": 1}))])
    llm([], system="s")                            # uses the only reply
    with pytest.raises(AssertionError, match="ran out"):
        llm([], system="s")                        # no reply left
