import os
from pathlib import Path
from pydantic import BaseModel

from coach.schemas import Plan
from coach.systems.scratch.state import RunState


class Checkpoint(BaseModel):
    state: RunState
    plan: Plan | None


def save_checkpoint(path: Path, ckpt: Checkpoint) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)      # make the folder if it's not there
    tmp = path.with_suffix(".tmp")                      # checkpoint.json -> checkpoint.tmp
    tmp.write_text(ckpt.model_dump_json(indent=2), encoding="utf-8")   # explicit: the Windows default is not UTF-8
    os.replace(tmp, path)                               # swap it in; this step is all-or-nothing


def load_checkpoint(path: Path) -> Checkpoint | None:
    if not path.exists():
        return None
    return Checkpoint.model_validate_json(path.read_text(encoding="utf-8"))