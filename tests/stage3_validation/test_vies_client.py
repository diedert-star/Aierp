from typing import Any

import httpx
import pytest

from aierp.stage3_validation.vies_client import ViesHttpClient


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return self._payload


def test_is_valid_returns_true_when_vies_confirms(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "aierp.stage3_validation.vies_client.httpx.get",
        lambda *a, **k: _FakeResponse({"isValid": True}),
    )
    client = ViesHttpClient(min_interval_seconds=0.0)
    assert client.is_valid("BE", "0123456749") is True


def test_is_valid_returns_false_when_vies_denies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "aierp.stage3_validation.vies_client.httpx.get",
        lambda *a, **k: _FakeResponse({"isValid": False}),
    )
    client = ViesHttpClient(min_interval_seconds=0.0)
    assert client.is_valid("BE", "0123456749") is False


def test_is_valid_returns_none_on_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: Any, **kwargs: Any) -> Any:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("aierp.stage3_validation.vies_client.httpx.get", _raise)
    client = ViesHttpClient(min_interval_seconds=0.0)
    assert client.is_valid("BE", "0123456749") is None


def test_result_is_cached_and_does_not_hit_network_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = 0

    def _get(*args: Any, **kwargs: Any) -> _FakeResponse:
        nonlocal call_count
        call_count += 1
        return _FakeResponse({"isValid": True})

    monkeypatch.setattr("aierp.stage3_validation.vies_client.httpx.get", _get)
    client = ViesHttpClient(min_interval_seconds=0.0, cache_ttl_seconds=3600.0)

    assert client.is_valid("BE", "0123456749") is True
    assert client.is_valid("BE", "0123456749") is True
    assert call_count == 1
