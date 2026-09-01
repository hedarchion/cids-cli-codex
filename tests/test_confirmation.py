"""Mutation confirmation contracts; no network calls are made."""

from __future__ import annotations

import importlib

import pytest


def _confirmation_callable():
    package = pytest.importorskip("cids_cli")
    module = getattr(package, "confirmation", None)
    if module is None:
        try:
            module = importlib.import_module("cids_cli.confirmation")
        except ModuleNotFoundError:
            pytest.skip("cids_cli has no confirmation module")
    for name in ("confirm_mutation", "require_confirmation", "confirm"):
        value = getattr(module, name, None)
        if value is not None:
            return value
    pytest.skip("cids_cli does not expose a mutation confirmation callable")


def test_declining_mutation_never_authorizes_request() -> None:
    confirm = _confirmation_callable()
    answers = iter(["n"])
    try:
        result = confirm("delete example report", input_fn=lambda _: next(answers))
    except (KeyboardInterrupt, EOFError):
        pytest.fail("confirmation prompt did not handle a user decline")
    except Exception as exc:  # cancellation exceptions are valid behavior
        assert "declin" in str(exc).lower() or "cancel" in str(exc).lower()
    else:
        assert result is False, "a declined mutation must not return authorization"


def test_non_mutating_operations_do_not_require_confirmation() -> None:
    confirm = _confirmation_callable()
    try:
        result = confirm("view example resource", mutation=False)
    except TypeError:
        pytest.skip("confirmation callable has no mutation/read distinction yet")
    assert result in (True, None), "read-only operations should proceed without a prompt"
