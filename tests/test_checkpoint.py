from coach.schemas import Evidence, Finding, Hypothesis, Plan
from coach.systems.scratch.checkpoint import Checkpoint, load_checkpoint, save_checkpoint
from coach.systems.scratch.state import RunState


def a_state():
    f = Finding(claim="Dragon Knight died 9 times – more than anyone.", verdict="supported", severity="major",
                evidence=[Evidence(kind="stat", player="Dragon Knight (Radiant)", metric="deaths", value=9)])
    return RunState(question="Why?", match_id=1, iteration=1, findings=[f], dropped=["H2"],
                    hypotheses_tried=["Radiant lost the fight."], tokens_spent=450, decisions=["replan: x"])


PLAN = Plan(hypotheses=[Hypothesis(id="H1", statement="Tusk bought blink late.", rationale="r")])


def test_checkpoint_round_trips_state_and_plan(tmp_path):
    path = tmp_path / "run" / "checkpoint.json"             # the folder does not exist yet
    save_checkpoint(path, Checkpoint(state=a_state(), plan=PLAN))
    loaded = load_checkpoint(path)

    assert loaded is not None
    assert loaded.state == a_state()                         # includes the non-ASCII dash in the claim
    assert loaded.plan == PLAN


def test_a_finished_run_is_saved_with_no_plan(tmp_path):
    path = tmp_path / "checkpoint.json"
    save_checkpoint(path, Checkpoint(state=a_state(), plan=None))
    loaded = load_checkpoint(path)
    assert loaded is not None and loaded.plan is None


def test_missing_file_means_no_checkpoint(tmp_path):
    assert load_checkpoint(tmp_path / "nothing.json") is None


def test_saving_again_replaces_the_old_checkpoint_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "checkpoint.json"
    save_checkpoint(path, Checkpoint(state=a_state(), plan=PLAN))
    save_checkpoint(path, Checkpoint(state=a_state(), plan=None))
    loaded = load_checkpoint(path)
    assert loaded is not None and loaded.plan is None
    assert [p.name for p in tmp_path.iterdir()] == ["checkpoint.json"]
