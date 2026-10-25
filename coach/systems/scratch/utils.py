from pydantic import ValidationError


def format_errors(e: ValidationError) -> str:
    return "\n".join(
        f"- {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()
    )