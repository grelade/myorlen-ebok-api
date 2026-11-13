"""Shared fixtures. All HTTP is mocked with ``responses``; fixtures under tests/fixtures are
anonymised captures of real ebok.myorlen.pl API responses."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import responses

from myorlen_ebok_api import MyorlenClient

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://ebok.myorlen.pl"
PPG = "8018590000000000000001"
AGREEMENT = "100/O/ABC/12345/09"
CLIENT = "1234567"
TOKEN = "test-token"


def fixture_json(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def mocked() -> Iterator[responses.RequestsMock]:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps


@pytest.fixture
def client(mocked: responses.RequestsMock) -> MyorlenClient:
    """A client that already holds a token (no login round-trip)."""
    c = MyorlenClient("user@example.com", "secret")
    c.token = TOKEN
    return c


def add_json(
    rsps: responses.RequestsMock, path: str, data: Any, method: str = "GET", status: int = 200
) -> None:
    rsps.add(method, BASE + path, json=data, status=status)


def add_fixture(rsps: responses.RequestsMock, path: str, fixture: str) -> None:
    add_json(rsps, path, fixture_json(fixture))


def login_ok(rsps: responses.RequestsMock, token: str = TOKEN) -> None:
    add_json(
        rsps,
        "/auth/login",
        {"Code": 0, "Token": token, "DateExpirationUtc": "2099-01-01T00:00:00.000000Z"},
        method="POST",
    )


@pytest.fixture
def ppg_list(mocked: responses.RequestsMock) -> None:
    add_fixture(mocked, "/crm/get-ppg-list", "ppg_list")
