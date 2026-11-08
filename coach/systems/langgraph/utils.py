from pydantic import ValidationError


def format_errors(e: ValidationError) -> str:
    return "\n".join(
        f"- {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()
    )


def block_text(r) -> str:
    return "".join(b["text"] for b in r if b.get("type") == "text")