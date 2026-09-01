"""Authentication safety contracts using fake values only."""

from __future__ import annotations

import importlib

import pytest


def _auth_module():
    package = pytest.importorskip("cids_cli")
    return getattr(package, "auth", None) or importlib.import_module("cids_cli.auth")


def _credential_type(module):
    for name in ("Credentials", "AuthConfig", "CredentialConfig"):
        value = getattr(module, name, None)
        if value is not None:
            return value
    pytest.skip("cids_cli.auth does not expose a credential value type")


def test_credential_repr_does_not_leak_password() -> None:
    module = _auth_module()
    credential_type = _credential_type(module)
    try:
        credentials = credential_type(username="example-user", password="example-secret")
    except TypeError:
        credentials = credential_type("example-user", "example-secret")
    assert "example-secret" not in repr(credentials)
    assert "example-secret" not in str(credentials)


def test_environment_loader_reads_supported_names_without_printing(monkeypatch, capsys) -> None:
    module = _auth_module()
    loader = next(
        (
            getattr(module, name, None)
            for name in ("resolve_credentials", "load_credentials", "credentials_from_env")
            if getattr(module, name, None) is not None
        ),
        None,
    )
    if loader is None:
        pytest.skip("cids_cli.auth does not expose an environment credential loader")
    monkeypatch.setenv("CIDS_USERNAME", "example-user")
    monkeypatch.setenv("CIDS_PASSWORD", "example-secret")
    try:
        result = loader()
    except TypeError:
        result = loader(environ=dict(CIDS_USERNAME="example-user", CIDS_PASSWORD="example-secret"))
    captured = capsys.readouterr()
    assert "example-secret" not in captured.out + captured.err
    assert result is not None
