"""Typed records returned by the SDK.

All money is ``Decimal`` (PLN), dates are ``datetime.date`` (timestamps ``datetime``).
``to_dict()`` gives a JSON-friendly ``dict`` (used by the CLI).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

_Date = date  # for annotations in classes that have a field called ``date``


def to_jsonable(value: Any) -> Any:
    """Recursively convert dataclasses/Decimal/date/Enum into JSON-serialisable values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


class _Record:
    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = to_jsonable(self)
        return result


# ---- enums -------------------------------------------------------------------


class InvoiceFilter(str, Enum):
    """Preset filters of ``get-invoices-v2`` (the tabs of the "Faktury" page)."""

    ALL = "all"
    UNPAID = "unpaid"  # paid=false
    OVERDUE = "overdue"  # afterDeadline=true
    FORECAST = "forecast"  # loadAfter30Days=true: forecast instalments due in more than 30 days


# ---- account -----------------------------------------------------------------


@dataclass
class Address(_Record):
    street: str | None = None
    street_type: str | None = None  # "ul.", "al.", ...
    building: str | None = None
    apartment: str | None = None
    postal_code: str | None = None
    city: str | None = None

    def __str__(self) -> str:
        street = " ".join(p for p in (self.street_type, self.street) if p)
        number = "/".join(p for p in (self.building, self.apartment) if p)
        first = " ".join(p for p in (street, number) if p)
        second = " ".join(p for p in (self.postal_code, self.city) if p)
        return ", ".join(p for p in (first, second) if p)


@dataclass
class User(_Record):
    """The logged-in eBOK user (``crm/get-user-data``)."""

    email: str | None
    first_name: str | None
    last_name: str | None
    pesel: str | None  # masked by the API, e.g. "800********"
    nip: str | None
    balance: Decimal | None  # Saldo: negative = overpayment
    amount_to_pay: Decimal | None
    billing: str | None
    has_prepaid: bool = False


@dataclass
class RelatedAccount(_Record):
    """A customer account linked to this login (``auth/get-related-accounts``)."""

    public_id: str
    client_number: str
    current: bool
    name: str | None = None


@dataclass
class CollectionPoint(_Record):
    osd_number: str  # PPG number at the distribution operator
    id_crd: str | None
    address: Address
    billing: str | None = None


@dataclass
class Agreement(_Record):
    """A supply agreement (``crm/get-agreements`` / ``crm/get-agreement-details``)."""

    number: str
    type: str  # "PPG" (gas), "PPE" (electricity), ...
    client_number: str
    ppg_number: str | None
    address: Address
    active: bool
    start_date: _Date | None
    end_date: _Date | None
    tariff: str | None
    client_name: str | None
    iban: str | None
    eco_invoice: bool
    balance: Decimal | None
    region: str | None
    name: str | None = None
    owner: bool | None = None
    correspondence_address: Address | None = None
    invoice_address: Address | None = None
    collection_points: list[CollectionPoint] = field(default_factory=list)


@dataclass
class MeterPoint(_Record):
    """A gas meter point (PPG) with its last reading (``crm/get-ppg-list``)."""

    id: str  # IdPPG, used by the readings / consumption endpoints
    meter_number: str | None
    address: Address
    agreement_number: str | None
    client_number: str | None
    tariff: str | None
    type: str | None
    local_id: str | None
    last_reading_date: _Date | None
    last_reading_value: Decimal | None
    reading_added: bool = False
    has_history: bool = False
    add_reading_mode: str | None = None


@dataclass
class BillingSummary(_Record):
    """Headline payment status (``crm/get-billing-summary``): ``Paid``, ``ToPay``, ``Overdue``, ..."""

    status: str | None
    value: Decimal | None


# ---- invoices & payments -----------------------------------------------------


@dataclass
class Invoice(_Record):
    """An invoice, forecast instalment or interest note (``crm/get-invoices-v2``)."""

    number: str
    date: _Date | None
    sell_date: _Date | None
    period_start: _Date | None
    period_end: _Date | None
    due_date: _Date | None
    gross_amount: Decimal | None
    amount_to_pay: Decimal | None
    is_paid: bool
    status: str | None
    type: str | None  # "PPG", ...
    kind: str | None  # TempType: "R" settlement, "B"/"P" forecast, "" for interest notes
    is_interest_note: bool
    is_credit_note: bool
    correction: bool
    agreement_number: str | None
    point_id: str | None  # IdPP
    consumption_kwh: Decimal | None
    consumption_m3: Decimal | None
    iban: str | None
    pdf_allowed: bool
    pdf_visibility: str | None = None  # details only: "PdfVisible" / "PdfHidden"
    automatic_payment_date: _Date | None = None  # details only: direct-debit date
    address: Address | None = None  # details only


@dataclass
class InvoicePage(_Record):
    items: list[Invoice]
    has_more: bool
    allow_load_all: bool = False


@dataclass
class Payment(_Record):
    """A payment booked on the account (``crm/get-client-payments``)."""

    date: _Date | None
    document_number: str | None
    amount: Decimal
    type: str | None
    description: str | None
    client_number: str | None
    transfer: bool = False


@dataclass
class HistoryEntry(_Record):
    """An entry of the account action history (``crm/get-account-history``)."""

    date: datetime | None
    type: str
    description: str | None


@dataclass
class DownloadedFile(_Record):
    filename: str | None
    content_type: str | None
    content: bytes = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {"filename": self.filename, "content_type": self.content_type, "size": len(self.content)}


# ---- readings & consumption --------------------------------------------------


@dataclass
class Reading(_Record):
    """A meter reading (``crm/get-all-ppg-readings-for-meter``). Values in m³."""

    date: _Date | None
    value: Decimal | None
    consumption: Decimal | None  # Wear since the previous reading
    type: str | None  # "Real", "Estimated", "Client", ...
    status: str | None  # "ROZL" = settled, "ANUL_KLIENT" = cancelled by customer, ...
    meter_number: str | None
    point_id: str | None
    client_number: str | None
    can_be_cancelled: bool = False
    value2: Decimal | None = None
    value3: Decimal | None = None
    consumption2: Decimal | None = None
    consumption3: Decimal | None = None


@dataclass
class ReadingPage(_Record):
    items: list[Reading]
    has_more: bool


@dataclass
class ConsumptionEntry(_Record):
    """One bar of the consumption charts (monthly or yearly)."""

    label: str
    year: str | None
    reading_date: _Date | None
    value: Decimal | None  # meter value
    consumption: Decimal | None  # m³
    type: int | None
    period: str | None = None
    zone: str | None = None


@dataclass
class YearConsumption(_Record):
    year: str
    total: Decimal | None
    entries: list[ConsumptionEntry] = field(default_factory=list)


@dataclass
class YearlyConsumption(_Record):
    """Year-over-year comparison (``crm/get-yearly-wear-chart-data``)."""

    comparison_percent: Decimal | None
    increase: bool
    this_year: list[YearConsumption]
    previous_year: list[YearConsumption]


# ---- messages ----------------------------------------------------------------


@dataclass
class Notification(_Record):
    id: str
    title: str
    body: str | None
    created: datetime | None
    type: str | None
    object_id: str | None = None


@dataclass
class ContactMessage(_Record):
    """An entry of the contact form history (``contact/get-contact-history-v2``)."""

    public_id: str | None
    subject: str | None
    date: datetime | None
    status: str | None
    type: str | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class EmailSettings(_Record):
    system: bool
    invoices: bool
