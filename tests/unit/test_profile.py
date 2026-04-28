"""Profile detection unit tests."""
from __future__ import annotations

import os

import pytest

from shared.profile import Profile, get_profile, is_azure, is_local


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("RUNTIME_PROFILE", raising=False)


def test_default_is_azure() -> None:
    assert get_profile() == Profile.AZURE
    assert is_azure() is True
    assert is_local() is False


def test_local_via_env(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_PROFILE", "local")
    assert get_profile() == Profile.LOCAL
    assert is_local() is True


def test_case_insensitive(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_PROFILE", "LOCAL")
    assert get_profile() == Profile.LOCAL
    monkeypatch.setenv("RUNTIME_PROFILE", "Azure")
    assert get_profile() == Profile.AZURE


def test_unknown_value_falls_back_to_azure(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_PROFILE", "kubernetes")
    assert get_profile() == Profile.AZURE
