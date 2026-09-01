"""Credential resolution with secret-safe representations."""

from __future__ import annotations

import getpass
import os
from dataclasses import dataclass
from typing import Callable, Mapping, Optional


@dataclass(frozen=True, repr=False)
class Credentials:
    username: str
    password: str

    def __repr__(self) -> str:
        return f"Credentials(username={self.username!r}, password='[REDACTED]')"

    __str__ = __repr__


def resolve_credentials(
    username: Optional[str] = None,
    password: Optional[str] = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
    input_fn: Callable[[str], str] = input,
    getpass_fn: Callable[[str], str] = getpass.getpass,
) -> Credentials:
    env = os.environ if environ is None else environ
    resolved_user = username or env.get("CIDS_USERNAME") or input_fn("CIDS username: ").strip()
    resolved_password = password or env.get("CIDS_PASSWORD") or getpass_fn("CIDS password: ")
    if not resolved_user or not resolved_password:
        raise ValueError("Both username and password are required.")
    return Credentials(resolved_user, resolved_password)
