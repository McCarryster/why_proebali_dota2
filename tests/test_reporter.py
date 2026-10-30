from coach.schemas import Evidence, Finding
import asyncio

import pytest

from coach.systems.scratch.mcp_tools import McpTools
from coach.systems.scratch.reporter import format_findings, write_report
from tests.fakes import FakeLLM, reply, tool_use
from coach.systems.scratch.state import RunState


def finding(claim, verdict="supported", severity="major"):
    return Finding(claim=claim, verdict=verdict, severity=severity,
                   evidence=[Evidence(kind="stat", player="Dragon Knight (Radiant)", metric="deaths", value=9)])


def test_findings_are_listed_with_verdict_and_severity():
    s = RunState(question="Why did Radiant lose?", match_id=1,
                 findings=[finding("Dragon Knight died 9 times."),
                           finding("Tusk bought blink late.", "inconclusive", "minor")],
                 dropped=["H2"])
    assert format_findings(s) == (
        "Question: Why did Radiant lose?\n"
        "\n"
        "Findings:\n"
        "1. [supported, major] Dragon Knight died 9 times.\n"
        "2. [inconclusive, minor] Tusk bought blink late.\n"
        "\n"
        "Hypotheses that could not be tested: H2"
    )


def test_no_dropped_line_when_nothing_was_dropped():
    s = RunState(question="Q?", match_id=1, findings=[finding("Claim.")])
    assert "could not be tested" not in format_findings(s)


def run(state, llm):
    async def go():
        async with McpTools() as tools:
            return await write_report(state, tools, llm_call=llm)
    return asyncio.run(go())


GOOD_DRAFT = {"answer": "Radiant lost because Dragon Knight kept dying.", "turning_point_s": 641, "unresolved": ["blink timing"]}


def test_report_attaches_validated_findings_sorted_and_without_inconclusive():
    s = RunState(question="Why?", match_id=1, findings=[
        finding("minor one", severity="minor"),
        finding("unclear one", "inconclusive", "major"),
        finding("decisive one", severity="decisive"),
        finding("major one", severity="major"),
    ])
    llm = FakeLLM([reply(tool_use("submit_report", GOOD_DRAFT))])
    report = run(s, llm)

    assert report.answer == GOOD_DRAFT["answer"]
    assert report.turning_point_s == 641
    assert [f.claim for f in report.key_findings] == ["decisive one", "major one", "minor one"]
    assert report.key_findings[0] is s.findings[2]           # the very objects that passed verification
    assert "Question: Why?" in llm.calls[0]["messages"][0]["content"]


def test_invalid_draft_is_sent_back_and_fixed():
    s = RunState(question="Why?", match_id=1, findings=[finding("Claim.")])
    llm = FakeLLM([reply(tool_use("submit_report", {"turning_point_s": "soon"})),     # no answer, bad number
                   reply(tool_use("submit_report", GOOD_DRAFT))])
    report = run(s, llm)

    assert report.answer == GOOD_DRAFT["answer"]
    feedback = llm.calls[1]["messages"][-1]["content"][0]
    assert feedback["is_error"] is True
    assert "answer" in feedback["content"]


def test_two_invalid_drafts_raise():
    s = RunState(question="Why?", match_id=1, findings=[finding("Claim.")])
    llm = FakeLLM([reply(tool_use("submit_report", {})), reply(tool_use("submit_report", {}))])
    with pytest.raises(RuntimeError, match="2 attempts"):
        run(s, llm)
    assert len(llm.calls) == 2


def test_report_is_still_written_with_no_findings():
    # The model is still asked: it can explain what stayed unresolved.
    s = RunState(question="Why?", match_id=1, dropped=["H1"])
    llm = FakeLLM([reply(tool_use("submit_report", dict(GOOD_DRAFT, turning_point_s=None)))])
    report = run(s, llm)
    assert report.key_findings == []
    assert len(llm.calls) == 1
