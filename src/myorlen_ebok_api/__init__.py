"""Unofficial Python SDK for the myORLEN gas eBOK (ebok.myorlen.pl, formerly PGNiG eBOK)."""

from importlib.metadata import PackageNotFoundError, version

from .client import BASE_URL, MyorlenClient
from .exceptions import ApiError, AuthenticationError, MyorlenError, NotFoundError, ParseError
from .models import (
    Address,
    Agreement,
    BillingSummary,
    CollectionPoint,
    ConsumptionEntry,
    ContactMessage,
    DownloadedFile,
    EmailSettings,
    HistoryEntry,
    Invoice,
    InvoiceFilter,
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

try:
    __version__ = version("myorlen-ebok-api")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0"

__all__ = [
    "BASE_URL",
    "Address",
    "Agreement",
    "ApiError",
    "AuthenticationError",
    "BillingSummary",
    "CollectionPoint",
    "ConsumptionEntry",
    "ContactMessage",
    "DownloadedFile",
    "EmailSettings",
    "HistoryEntry",
    "Invoice",
    "InvoiceFilter",
    "InvoicePage",
    "MeterPoint",
    "MyorlenClient",
    "MyorlenError",
    "NotFoundError",
    "Notification",
    "ParseError",
    "Payment",
    "Reading",
    "ReadingPage",
    "RelatedAccount",
    "User",
    "YearConsumption",
    "YearlyConsumption",
    "__version__",
]
