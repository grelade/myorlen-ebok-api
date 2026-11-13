"""Pure functions turning eBOK JSON responses into models. No I/O here.

The API answers JSON objects in PascalCase with a common envelope
(``Code``, ``Message``, ``TokenExpireDate``, ...). Timestamps look like
``2026-10-27T00:00:00.000000Z``; amounts are JSON numbers (converted through ``str`` to
keep ``Decimal`` exact).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from .exceptions import ParseError
from .models import (
    Address,
    Agreement,
    BillingSummary,
    CollectionPoint,
    ConsumptionEntry,
    ContactMessage,
    EmailSettings,
    HistoryEntry,
    Invoice,
    InvoicePage,
    MeterPoint,
    Notification,
    Payment,
    Reading,
    ReadingPage,
    RelatedAccount,
    User,
    YearConsumption,
    YearlyConsumption,
)

Json = Mapping[str, Any]


# ---- scalars -----------------------------------------------------------------


def to_datetime(value: Any) -> datetime | None:
    """``2026-10-27T00:00:00.000000Z`` (or without fraction / zone) -> aware ``datetime``."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # Python 3.10 fromisoformat only accepts 0, 3 or 6 fractional digits
        head, _, rest = text.partition(".")
        frac = "".join(c for c in rest if c.isdigit())
        zone = rest[len(frac) :]
        try:
            dt = datetime.fromisoformat(f"{head}.{frac[:6].ljust(6, '0')}{zone}" if frac else head + zone)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def to_date(value: Any) -> date | None:
    dt = to_datetime(value)
    return dt.date() if dt else None


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", ".").replace(" ", ""))
    except InvalidOperation:
        return None


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool(value: Any) -> bool:
    return bool(value)


def _list(data: Json, key: str, what: str) -> list[Any]:
    if not isinstance(data, Mapping):
        raise ParseError(f"{what}: expected an object, got {type(data).__name__}")
    items = data.get(key)
    if items is None:
        return []
    if not isinstance(items, list):
        raise ParseError(f"{what}: {key} is not a list")
    return items


def _obj(data: Json, key: str, what: str) -> Json:
    if not isinstance(data, Mapping) or not isinstance(data.get(key), Mapping):
        raise ParseError(f"{what}: missing {key}")
    obj: Json = data[key]
    return obj


# ---- account -----------------------------------------------------------------


def parse_address(data: Json | None) -> Address:
    """Both address shapes: Polish keys (``Ulica``/``NrBudynku``...) and the flat
    ``AddressStreet``... keys of collection points."""
    if not data:
        return Address()
    if "AddressCity" in data or "AddressStreet" in data:
        return Address(
            street=_str(data.get("AddressStreet")),
            street_type=_str(data.get("AddressStreetFeature")),
            building=_str(data.get("AddressBuildingNumber")),
            apartment=_str(data.get("AddressApartmentNumber")),
            postal_code=_str(data.get("AddressPostalCode")),
            city=_str(data.get("AddressCity")),
        )
    return Address(
        street=_str(data.get("Ulica")),
        street_type=_str(data.get("UlicaTyp")),
        building=_str(data.get("NrBudynku")),
        apartment=_str(data.get("NrLokalu")),
        postal_code=_str(data.get("KodPocztowy")),
        city=_str(data.get("Miejscowosc")),
    )


def parse_user(data: Json) -> User:
    if not isinstance(data, Mapping):
        raise ParseError("get-user-data: expected an object")
    return User(
        email=_str(data.get("Email")),
        first_name=_str(data.get("FirstName")),
        last_name=_str(data.get("LastName")),
        pesel=_str(data.get("Pesel")),
        nip=_str(data.get("Nip")),
        balance=to_decimal(data.get("Saldo")),
        amount_to_pay=to_decimal(data.get("AmountToPay")),
        billing=_str(data.get("Billing")),
        has_prepaid=_bool(data.get("HasPrepaid")),
    )


def parse_related_accounts(data: Json) -> list[RelatedAccount]:
    return [
        RelatedAccount(
            public_id=str(a.get("PublicId") or ""),
            client_number=str(a.get("ClientNumber") or ""),
            current=_bool(a.get("Current")),
            name=_str(a.get("ClientName")),
        )
        for a in _list(data, "RelatedAccounts", "get-related-accounts")
    ]


def parse_collection_point(data: Json) -> CollectionPoint:
    return CollectionPoint(
        osd_number=str(data.get("NumberOSD") or ""),
        id_crd=_str(data.get("IdCRD")),
        address=parse_address(data),
        billing=_str(data.get("Billing")),
    )


def parse_agreement(data: Json) -> Agreement:
    """One agreement, from either the list (``get-agreements``) or ``get-agreement-details``."""
    if not data.get("AgreementNumber"):
        raise ParseError("agreement without AgreementNumber")
    owner = data.get("Owner", data.get("IsOwner"))
    return Agreement(
        number=str(data["AgreementNumber"]),
        type=str(data.get("Type") or ""),
        client_number=str(data.get("ClientNumber") or ""),
        ppg_number=_str(data.get("PpNumber")),
        address=parse_address(data.get("Address")),
        active=_bool(data.get("Active")),
        start_date=to_date(data.get("StartDate")),
        end_date=to_date(data.get("EndDate")),
        tariff=_str(data.get("Tariff")),
        client_name=_str(data.get("ClientName")),
        iban=_str(data.get("Iban")),
        eco_invoice=_bool(data.get("EcoInvoice")),
        balance=to_decimal(data.get("Saldo")),
        region=_str(data.get("Region")),
        name=_str(data.get("AgreementName")),
        owner=None if owner is None else bool(owner),
        correspondence_address=(
            parse_address(data["AddressForCorrespondence"]) if data.get("AddressForCorrespondence") else None
        ),
        invoice_address=parse_address(data["InvoiceAddress"]) if data.get("InvoiceAddress") else None,
        collection_points=[parse_collection_point(c) for c in data.get("CollectionPoints") or []],
    )


def parse_agreements(data: Json) -> list[Agreement]:
    return [parse_agreement(a) for a in _list(data, "Agreements", "get-agreements")]


def parse_agreement_details(data: Json) -> Agreement:
    return parse_agreement(_obj(data, "Agreement", "get-agreement-details"))


def parse_meter_points(data: Json) -> list[MeterPoint]:
    out = []
    for p in _list(data, "PpgList", "get-ppg-list"):
        if not p.get("IdPPG"):
            raise ParseError("get-ppg-list: entry without IdPPG")
        out.append(
            MeterPoint(
                id=str(p["IdPPG"]),
                meter_number=_str(p.get("MeterNumber")),
                address=parse_address(p.get("Address")),
                agreement_number=_str(p.get("ContractNumber")),
                client_number=_str(p.get("ClientNumber")),
                tariff=_str(p.get("Tariff")),
                type=_str(p.get("Type")),
                local_id=_str(p.get("IdLocal")),
                last_reading_date=to_date(p.get("ReadingDateUtc")),
                last_reading_value=to_decimal(p.get("ReadingValue")),
                reading_added=_bool(p.get("ReadingAdded")),
                has_history=_bool(p.get("HasHistory")),
                add_reading_mode=_str(p.get("AddReadingMode")),
            )
        )
    return out


def parse_billing_summary(data: Json) -> BillingSummary:
    if not isinstance(data, Mapping):
        raise ParseError("get-billing-summary: expected an object")
    return BillingSummary(status=_str(data.get("Status")), value=to_decimal(data.get("Value")))


# ---- invoices & payments -----------------------------------------------------


def parse_invoice(data: Json) -> Invoice:
    """An invoice from the list or from ``get-invoice-details`` (``{"Invoice": {...}}``)."""
    if not data.get("Number"):
        raise ParseError("invoice without Number")
    return Invoice(
        number=str(data["Number"]),
        date=to_date(data.get("Date")),
        sell_date=to_date(data.get("SellDate")),
        period_start=to_date(data.get("StartDate")),
        period_end=to_date(data.get("EndDate")),
        due_date=to_date(data.get("PayingDeadlineDate")),
        gross_amount=to_decimal(data.get("GrossAmount")),
        amount_to_pay=to_decimal(data.get("AmountToPay")),
        is_paid=_bool(data.get("IsPaid")),
        status=_str(data.get("Status")),
        type=_str(data.get("Type")),
        kind=_str(data.get("TempType")),
        is_interest_note=_bool(data.get("IsInterestNote")),
        is_credit_note=_bool(data.get("IsCreditNote")),
        correction=_bool(data.get("Correction")),
        agreement_number=_str(data.get("AgreementNumber")),
        point_id=_str(data.get("IdPP")),
        consumption_kwh=to_decimal(data.get("WearKWH")),
        consumption_m3=to_decimal(data.get("WearM3")),
        iban=_str(data.get("Iban")),
        pdf_allowed=_bool(data.get("PDFPrintAllowed")),
        pdf_visibility=_str(data.get("PdfVisibility")),
        automatic_payment_date=to_date(data.get("AutomaticPaymentDate")),
        address=parse_address(data["Address"]) if data.get("Address") else None,
    )


def parse_invoice_page(data: Json) -> InvoicePage:
    return InvoicePage(
        items=[parse_invoice(i) for i in _list(data, "InvoicesList", "get-invoices-v2")],
        has_more=_bool(data.get("HasMoreRecords")),
        allow_load_all=_bool(data.get("AllowLoadAllInvoices")),
    )


def parse_invoice_details(data: Json) -> Invoice:
    return parse_invoice(_obj(data, "Invoice", "get-invoice-details"))


def parse_interest_note_details(data: Json) -> Invoice:
    """``get-interest-note-details`` uses different keys; map them onto ``Invoice``."""
    n = _obj(data, "InterestNote", "get-interest-note-details")
    number = n.get("DocumentNumber") or n.get("InvoiceNumber")
    if not number:
        raise ParseError("interest note without DocumentNumber")
    return Invoice(
        number=str(number),
        date=to_date(n.get("DateCreated")),
        sell_date=to_date(n.get("DateSell")),
        period_start=None,
        period_end=None,
        due_date=to_date(n.get("DatePaymentDeadline")),
        gross_amount=to_decimal(n.get("GrossAmount")),
        amount_to_pay=to_decimal(n.get("AmountToPay")),
        is_paid=_bool(n.get("IsPaid")),
        status=_str(n.get("Status")),
        type=_str(n.get("Type")),
        kind=_str(n.get("DocumentType")),
        is_interest_note=True,
        is_credit_note=False,
        correction=False,
        agreement_number=_str(n.get("AgreementNumber")),
        point_id=_str(n.get("IdPP")),
        consumption_kwh=None,
        consumption_m3=None,
        iban=_str(n.get("Iban")),
        pdf_allowed=_bool(n.get("PDFPrintAllowed")),
        pdf_visibility=_str(n.get("PdfVisibility")),
        automatic_payment_date=to_date(n.get("AutomaticPaymentDate")),
    )


def parse_payments(data: Json) -> list[Payment]:
    out = []
    for p in _list(data, "Payments", "get-client-payments"):
        amount = to_decimal(p.get("Value"))
        if amount is None:
            raise ParseError("payment without Value")
        out.append(
            Payment(
                date=to_date(p.get("DocumentDate")),
                document_number=_str(p.get("DocumentNumber")),
                amount=amount,
                type=_str(p.get("PaymentType")),
                description=_str(p.get("Description")),
                client_number=_str(p.get("ClientNumber")),
                transfer=_bool(p.get("Transfer")),
            )
        )
    return out


def parse_history(data: Json) -> list[HistoryEntry]:
    return [
        HistoryEntry(
            date=to_datetime(h.get("Date")),
            type=str(h.get("Type") or ""),
            description=_str(h.get("Description")),
        )
        for h in _list(data, "HistoryList", "get-account-history")
    ]


# ---- readings & consumption --------------------------------------------------


def parse_reading(r: Json) -> Reading:
    return Reading(
        date=to_date(r.get("ReadingDateUtc")),
        value=to_decimal(r.get("Value")),
        consumption=to_decimal(r.get("Wear")),
        type=_str(r.get("Type")),
        status=_str(r.get("Status")),
        meter_number=_str(r.get("MeterNumber")),
        point_id=_str(r.get("PpId")),
        client_number=_str(r.get("ClientNumber")),
        can_be_cancelled=_bool(r.get("CanBeCancelled")),
        value2=to_decimal(r.get("Value2")),
        value3=to_decimal(r.get("Value3")),
        consumption2=to_decimal(r.get("Wear2")),
        consumption3=to_decimal(r.get("Wear3")),
    )


def parse_reading_page(data: Json) -> ReadingPage:
    return ReadingPage(
        items=[parse_reading(r) for r in _list(data, "MeterReadings", "get-all-ppg-readings-for-meter")],
        has_more=_bool(data.get("HasMoreRecords")),
    )


def parse_reading_dates(data: Json) -> list[date]:
    out = [to_date(d) for d in _list(data, "MeterReadingsDates", "get-ppg-readings-dates")]
    return [d for d in out if d is not None]


def _consumption_entry(e: Json, year: str | None = None) -> ConsumptionEntry:
    t = e.get("Type")
    return ConsumptionEntry(
        label=str(e.get("Label") or ""),
        year=_str(e.get("Year")) or year,
        reading_date=to_date(e.get("ReadingDateUtc")),
        value=to_decimal(e.get("Value")),
        consumption=to_decimal(e.get("Wear")),
        type=t if isinstance(t, int) else None,
        period=_str(e.get("Period")),
        zone=_str(e.get("ZoneLabel")),
    )


def parse_monthly_consumption(data: Json) -> list[ConsumptionEntry]:
    """``ChartData`` is ``{"<month>_<year>": [entry, ...]}``; flattened, oldest first."""
    chart = _obj(data, "ChartData", "get-monthly-wear-chart-data")
    entries = [_consumption_entry(e) for group in chart.values() for e in (group or [])]
    return sorted(entries, key=lambda e: (e.reading_date or date.min, e.zone or ""))


def _years(items: Any) -> list[YearConsumption]:
    out = []
    for y in items or []:
        year = str(y.get("Year") or "")
        out.append(
            YearConsumption(
                year=year,
                total=to_decimal(y.get("WearByYear")),
                entries=[_consumption_entry(e, year) for e in y.get("ChartItems") or []],
            )
        )
    return out


def parse_yearly_consumption(data: Json) -> YearlyConsumption:
    if not isinstance(data, Mapping) or "ThisYearData" not in data:
        raise ParseError("get-yearly-wear-chart-data: missing ThisYearData")
    return YearlyConsumption(
        comparison_percent=to_decimal(data.get("ComparisonPercent")),
        increase=_bool(data.get("IsPlusSignForPercent")),
        this_year=_years(data.get("ThisYearData")),
        previous_year=_years(data.get("PreviousYearData")),
    )


# ---- messages ----------------------------------------------------------------


def parse_notifications(data: Json) -> list[Notification]:
    return [
        Notification(
            id=str(n.get("Id") or ""),
            title=str(n.get("Title") or ""),
            body=_str(n.get("Body")),
            created=to_datetime(n.get("DateCreatedUtc")),
            type=_str(n.get("Type")),
            object_id=_str(n.get("ObjectId")),
        )
        for n in _list(data, "Notifications", "get-notifications")
    ]


def _first(d: Json, *keys: str) -> Any:
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def parse_contact_history(data: Json) -> tuple[list[ContactMessage], bool]:
    """Contact-form history. The item shape was not observed on a live account (the test
    account had none), so the known fields are best-effort and ``raw`` keeps everything."""
    items = [
        ContactMessage(
            public_id=_str(_first(c, "PublicId", "Id")),
            subject=_str(_first(c, "Subject", "Title", "Topic")),
            date=to_datetime(_first(c, "DateCreatedUtc", "DateCreated", "Date", "CreatedDate")),
            status=_str(_first(c, "Status", "StatusName")),
            type=_str(c.get("Type")),
            raw=dict(c),
        )
        for c in _list(data, "Contacts", "get-contact-history-v2")
    ]
    return items, _bool(data.get("AllowLoadMore"))


def parse_email_settings(data: Json) -> EmailSettings:
    s = _obj(data, "Settings", "email-settings")
    return EmailSettings(system=_bool(s.get("System")), invoices=_bool(s.get("Invoices")))
