"""Read-only smoke tests against the real ebok.myorlen.pl.

Skipped unless MYORLEN_LIVE=1 and MYORLEN_USER / MYORLEN_PASS are set (a .env file in the
project root works too). Run with: ``MYORLEN_LIVE=1 uv run pytest -m live``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from myorlen_ebok_api import ApiError, MyorlenClient
from myorlen_ebok_api.cli import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")
for _new, _old in (("MYORLEN_USER", "PGNIG_USER"), ("MYORLEN_PASS", "PGNIG_PASS")):
    if _old in os.environ:
        os.environ.setdefault(_new, os.environ[_old])

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (
            os.environ.get("MYORLEN_LIVE") == "1"
            and os.environ.get("MYORLEN_USER")
            and os.environ.get("MYORLEN_PASS")
        ),
        reason="set MYORLEN_LIVE=1 and MYORLEN_USER/MYORLEN_PASS to run live tests",
    ),
]


@pytest.fixture(scope="module")
def live() -> Iterator[MyorlenClient]:
    with MyorlenClient(os.environ["MYORLEN_USER"], os.environ["MYORLEN_PASS"]) as c:
        yield c


def test_account(live: MyorlenClient) -> None:
    assert live.get_user().email
    assert live.get_related_accounts()
    assert live.get_billing_summary().status
    agreements = live.get_agreements(include_inactive=True)
    assert agreements
    assert live.get_agreement(agreements[0].number).number == agreements[0].number


def test_invoices_and_pdf(live: MyorlenClient) -> None:
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


def test_payments_and_messages(live: MyorlenClient) -> None:
    assert isinstance(live.get_payments(), list)
    assert isinstance(live.get_account_history(), list)
    assert isinstance(live.get_notifications(), list)
    assert isinstance(live.get_contact_history(), list)
    live.get_email_settings()


def test_readings(live: MyorlenClient) -> None:
    point = live.get_meter_points()[0]
    assert point.id
    assert isinstance(live.get_readings(point.id).items, list)
    assert isinstance(live.get_monthly_consumption(point.id), list)
    live.get_yearly_consumption(point.id)
    assert live.export_readings(point.id).content
