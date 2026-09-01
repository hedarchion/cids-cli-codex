"""Reusable confirmation helper for callers embedding the CLI."""

from typing import Callable


def confirm_mutation(
    description: str,
    *,
    mutation: bool = True,
    input_fn: Callable[[str], str] = input,
) -> bool:
    if not mutation:
        return True
    answer = input_fn(f"Proceed with {description}? [y/N] ").strip().lower()
    return answer in {"y", "yes"}
