from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from myorlen_ebok_api import ParseError, parsers
from myorlen_ebok_api.models import Address

from .conftest import AGREEMENT, CLIENT, PPG, fixture_json


def test_scalars() -> None:
    assert parsers.to_date("2026-10-27T00:00:00.000000Z") == date(2026, 10, 27)
    assert parsers.to_datetime("2022-10-26T18:42:23.373000Z") == datetime(
        2022, 10, 26, 18, 42, 23, 373000, tzinfo=timezone.utc
    )
    assert parsers.to_datetime("2026-11-13T19:24:17.2442Z") is not None  # 4 fractional digits
    assert parsers.to_datetime("2026-11-13T19:24:17") == datetime(
        2026, 11, 13, 19, 24, 17, tzinfo=timezone.utc
    )
    assert parsers.to_date(None) is None
    assert parsers.to_date("garbage") is None
    assert parsers.to_decimal(628.26) == Decimal("628.26")
    assert parsers.to_decimal("1 234,50") == Decimal("1234.50")
    assert parsers.to_decimal(None) is None
    assert parsers.to_decimal("x") is None


def test_address_shapes() -> None:
    a = parsers.parse_address(
        {"Ulica": "Testowa", "UlicaTyp": "ul.", "NrBudynku": "1a", "NrLokalu": "2", "KodPocztowy": "00-001",
         "Miejscowosc": "Warszawa"}
    )  # fmt: skip
    assert str(a) == "ul. Testowa 1a/2, 00-001 Warszawa"
    b = parsers.parse_address({"AddressStreet": "Testowa", "AddressBuildingNumber": "1a", "AddressCity": "X"})
    assert b == Address(street="Testowa", building="1a", city="X")
    assert parsers.parse_address(None) == Address()
    assert str(parsers.parse_address({"NrLokalu": " "})) == ""


def test_user() -> None:
    u = parsers.parse_user(fixture_json("user_data"))
    assert u.email == "jan.kowalski@example.com"
    assert u.first_name == "Jan"
    assert u.balance == Decimal("0.0")
    assert u.pesel == "800********"
    with pytest.raises(ParseError):
        parsers.parse_user([])  # type: ignore[arg-type]


def test_related_accounts() -> None:
    (a,) = parsers.parse_related_accounts(fixture_json("related"))
    assert a.current and a.client_number == "7654321" and a.name is None


def test_agreements() -> None:
    (a,) = parsers.parse_agreements(fixture_json("agreements"))
    assert a.number == AGREEMENT
    assert a.client_number == CLIENT
    assert a.ppg_number == PPG
    assert a.type == "PPG" and a.active and a.owner
    assert a.start_date == date(2009, 11, 12) and a.end_date is None
    assert a.tariff == "W-2.1"
    assert a.address.city == "Warszawa"
    assert a.collection_points[0].osd_number == PPG
    assert a.collection_points[0].address.street == "Testowa"
    assert a.correspondence_address is None


def test_agreement_details() -> None:
    a = parsers.parse_agreement_details(fixture_json("agreement_details"))
    assert a.number == AGREEMENT
    assert a.owner is True
    assert a.correspondence_address is not None and a.correspondence_address.city == "Warszawa"
    with pytest.raises(ParseError):
        parsers.parse_agreement_details({"Code": 0})
    with pytest.raises(ParseError):
        parsers.parse_agreement({"Type": "PPG"})


def test_meter_points() -> None:
    (p,) = parsers.parse_meter_points(fixture_json("ppg_list"))
    assert p.id == PPG
    assert p.agreement_number == AGREEMENT
    assert p.last_reading_date == date(2026, 10, 27)
    assert p.last_reading_value == Decimal("2238.0")
    assert p.has_history
    with pytest.raises(ParseError):
        parsers.parse_meter_points({"PpgList": [{"MeterNumber": "x"}]})
    with pytest.raises(ParseError):
        parsers.parse_meter_points({"PpgList": "nope"})


def test_billing_summary() -> None:
    s = parsers.parse_billing_summary(fixture_json("billing_summary"))
    assert s.status == "Paid" and s.value is None


def test_invoice_page() -> None:
    page = parsers.parse_invoice_page(fixture_json("invoices"))
    assert page.has_more and len(page.items) == 12
    note, settlement, forecast = page.items[:3]
    assert note.is_interest_note and note.number.startswith("NO/") and note.kind is None
    assert settlement.kind == "R"
    assert settlement.gross_amount == Decimal("628.26")
    assert settlement.consumption_kwh == Decimal("5602.0")
    assert settlement.period_start == date(2025, 10, 15)
    assert settlement.due_date == date(2026, 11, 10)
    assert settlement.is_paid and settlement.pdf_allowed
    assert forecast.kind == "B"
    assert not parsers.parse_invoice_page(fixture_json("invoices_p2")).has_more


def test_invoice_details() -> None:
    inv = parsers.parse_invoice_details(fixture_json("invoice_details"))
    assert inv.number == "P/1234567/0001/26"
    assert inv.pdf_visibility == "PdfHidden"
    assert inv.automatic_payment_date == date(2026, 11, 8)
    assert inv.address is not None and inv.address.city == "Warszawa"
    assert inv.consumption_m3 == Decimal("487.0")


def test_interest_note_details() -> None:
    n = parsers.parse_interest_note_details(fixture_json("note_details"))
    assert n.number == "NO/1234567/000001/26"
    assert n.is_interest_note
    assert n.gross_amount == Decimal("0.22")
    assert n.due_date == date(2026, 11, 10)
    with pytest.raises(ParseError):
        parsers.parse_interest_note_details({"InterestNote": {}})


def test_payments() -> None:
    payments = parsers.parse_payments(fixture_json("client_payments"))
    assert len(payments) == 14
    p = payments[0]
    assert p.date == date(2026, 10, 29)
    assert p.amount == Decimal("628.48")
    assert p.document_number == "KP/RAP/BANK/26/000000/00/000001"
    with pytest.raises(ParseError):
        parsers.parse_payments({"Payments": [{"DocumentNumber": "x"}]})


def test_history() -> None:
    h = parsers.parse_history(fixture_json("account_history"))
    assert h and h[0].type == "Zapłata za fakturę"
    assert h[0].date is not None and h[0].date.year == 2022


def test_readings() -> None:
    page = parsers.parse_reading_page(fixture_json("readings"))
    assert not page.has_more
    r = page.items[0]
    assert r.date == date(2026, 10, 27)
    assert r.value == Decimal("2238.0") and r.consumption == Decimal("487.0")
    assert r.type == "Real" and r.status == "ROZL"
    assert r.value2 is None
    assert parsers.parse_reading_dates(fixture_json("reading_dates")) == [
        date(2026, 10, 27),
        date(2025, 10, 14),
    ]


def test_monthly_consumption() -> None:
    (e,) = parsers.parse_monthly_consumption(fixture_json("monthly"))
    assert e.label == "październik 2026" and e.year == "2026"
    assert e.consumption == Decimal("487.0")
    assert e.period == "14.10.2025 - 27.10.2026"
    multi = parsers.parse_monthly_consumption(
        {"ChartData": {"b": [{"Label": "b", "ReadingDateUtc": "2026-02-01T00:00:00Z"}],
                       "a": [{"Label": "a", "ReadingDateUtc": "2026-01-01T00:00:00Z"}]}}
    )  # fmt: skip
    assert [m.label for m in multi] == ["a", "b"]


def test_yearly_consumption() -> None:
    y = parsers.parse_yearly_consumption(fixture_json("yearly"))
    assert y.comparison_percent == Decimal("15.0") and not y.increase
    assert y.this_year[0].year == "2026" and y.this_year[0].total == Decimal("487.0")
    assert y.previous_year[0].entries[0].year == "2025"
    with pytest.raises(ParseError):
        parsers.parse_yearly_consumption({})


def test_notifications() -> None:
    n = parsers.parse_notifications(fixture_json("notifications"))
    assert len(n) == 4
    assert n[0].title == "Nowe faktury do zapłaty" and n[0].type == "Invoices"
    assert n[1].object_id == "P/1234567/0001/25/5"


def test_contact_history_and_settings() -> None:
    assert parsers.parse_contact_history(fixture_json("contact_history")) == ([], False)
    items, more = parsers.parse_contact_history(
        {"Contacts": [{"PublicId": "p1", "Subject": "Faktura", "DateCreated": "2026-01-02T03:04:05Z"}],
         "AllowLoadMore": True}
    )  # fmt: skip
    assert more and items[0].public_id == "p1" and items[0].subject == "Faktura"
    assert items[0].raw["PublicId"] == "p1"
    s = parsers.parse_email_settings(fixture_json("email_notif"))
    assert s.system and s.invoices
