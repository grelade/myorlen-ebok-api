"""Read-only smoke tests against the real ebok.myorlen.pl.

Skipped unless PGNIG_LIVE=1 and PGNIG_USER / PGNIG_PASS are set (a .env file in the
project root works too). Run with: ``PGNIG_LIVE=1 uv run pytest -m live``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from pgnig_ebok_api import ApiError, PgnigClient
from pgnig_ebok_api.cli import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (
            os.environ.get("PGNIG_LIVE") == "1"
            and os.environ.get("PGNIG_USER")
            and os.environ.get("PGNIG_PASS")
        ),
        reason="set PGNIG_LIVE=1 and PGNIG_USER/PGNIG_PASS to run live tests",
    ),
]


@pytest.fixture(scope="module")
def live() -> Iterator[PgnigClient]:
    with PgnigClient(os.environ["PGNIG_USER"], os.environ["PGNIG_PASS"]) as c:
        yield c


def test_account(live: PgnigClient) -> None:
    assert live.get_user().email
    assert live.get_related_accounts()
    assert live.get_billing_summary().status
    agreements = live.get_agreements(include_inactive=True)
    assert agreements
    assert live.get_agreement(agreements[0].number).number == agreements[0].number


def test_invoices_and_pdf(live: PgnigClient) -> None:
    page = live.get_invoices(page_size=5)
    assert page.items
    inv = page.items[0]
    assert live.get_invoice(inv.number).number == inv.number
    regular = next((i for i in page.items if not i.is_interest_note and i.pdf_allowed), None)
    if regular is not None:
        try:
            assert live.download_invoice(regular).content.startswith(b"%PDF")
        except ApiError:
            pytest.skip("portal has no PDF for this invoice")


def test_payments_and_messages(live: PgnigClient) -> None:
    assert isinstance(live.get_payments(), list)
    assert isinstance(live.get_account_history(), list)
    assert isinstance(live.get_notifications(), list)
    assert isinstance(live.get_contact_history(), list)
    live.get_email_settings()


def test_readings(live: PgnigClient) -> None:
    point = live.get_meter_points()[0]
    assert point.id
    assert isinstance(live.get_readings(point.id).items, list)
    assert isinstance(live.get_monthly_consumption(point.id), list)
    live.get_yearly_consumption(point.id)
    assert live.export_readings(point.id).content
