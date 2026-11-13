"""Unofficial Python SDK for the PGNiG / myORLEN gas eBOK (ebok.myorlen.pl)."""

from importlib.metadata import PackageNotFoundError, version

from .client import BASE_URL, PgnigClient
from .exceptions import ApiError, AuthenticationError, NotFoundError, ParseError, PgnigError
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
    __version__ = version("pgnig-ebok-api")
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
    "NotFoundError",
    "Notification",
    "ParseError",
    "Payment",
    "PgnigClient",
    "PgnigError",
    "Reading",
    "ReadingPage",
    "RelatedAccount",
    "User",
    "YearConsumption",
    "YearlyConsumption",
    "__version__",
]
