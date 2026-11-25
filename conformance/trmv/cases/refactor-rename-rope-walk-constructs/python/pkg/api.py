from typing import Annotated


def field(description: str) -> str:
    return description


async def probe(p: Annotated[str | None, field(description="param text")] = None) -> str:
    """Docstring text."""
    return query(f"{p}" "(")


def query(user: str) -> str:
    return (
        "SELECT count() FROM system.query_log WHERE type = 'QueryFinish' "
        f"AND user = '{user}' "
        "AND query LIKE '%getSetting(%readonly%'"
    )
