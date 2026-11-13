"""HTTP client for the PGNiG / myORLEN eBOK (https://ebok.myorlen.pl, formerly ebok.pgnig.pl).

The portal is a React single-page app over a JSON API on the same host. Login returns a
token that every request sends in the ``AuthToken`` header; all calls carry the query
parameter ``api-version=3.0``. See API.md for the endpoint reference.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests

from . import parsers
from .exceptions import ApiError, AuthenticationError, NotFoundError
from .models import (
    Agreement,
    BillingSummary,
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
    YearlyConsumption,
)

log = logging.getLogger(__name__)

BASE_URL = "https://ebok.myorlen.pl"
API_VERSION = "3.0"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"
)
DEVICE_NAME = "pgnig-ebok-api"

# endpoints (paths relative to BASE_URL)
EP_LOGIN = "/auth/login"
EP_LOGOUT = "/auth/logout"
EP_RELATED_ACCOUNTS = "/auth/get-related-accounts"
EP_USER = "/crm/get-user-data"
EP_AGREEMENTS = "/crm/get-agreements"
EP_ALL_AGREEMENTS = "/crm/get-all-agreements"
EP_AGREEMENT_DETAILS = "/crm/get-agreement-details"
EP_PPG_LIST = "/crm/get-ppg-list"
EP_BILLING_SUMMARY = "/crm/get-billing-summary"
EP_INVOICES = "/crm/get-invoices-v2"
EP_INVOICE_DETAILS = "/crm/get-invoice-details"
EP_INTEREST_NOTE_DETAILS = "/crm/get-interest-note-details"
EP_INVOICE_PDF = "/crm/get-invoice-pdf"
EP_INTEREST_NOTE_PDF = "/crm/get-interest-note-pdf"
EP_PAYMENTS = "/crm/get-client-payments"
EP_HISTORY = "/crm/get-account-history"
EP_READINGS = "/crm/get-all-ppg-readings-for-meter"
EP_READING_DATES = "/crm/get-ppg-readings-dates"
EP_READINGS_FILE = "/crm/get-ppgs-readings-file"
EP_MONTHLY = "/crm/get-monthly-wear-chart-data"
EP_YEARLY = "/crm/get-yearly-wear-chart-data"
EP_NOTIFICATIONS = "/notification/get-notifications"
EP_UNREAD = "/notification/get-unreaded-count"
EP_EMAIL_SETTINGS = "/notification/email-settings"
EP_CONTACT_HISTORY = "/contact/get-contact-history-v2"

# Code values seen in login answers (from the web app's error messages)
LOGIN_ERRORS = {
    1011: "unauthorised device",
    1015: "user not found",
    1018: "account not activated",
    1025: "user temporarily blocked, try again in 5 minutes",
}

_INVOICE_FILTERS: dict[InvoiceFilter, dict[str, str]] = {
    InvoiceFilter.ALL: {},
    InvoiceFilter.UNPAID: {"paid": "false"},
    InvoiceFilter.OVERDUE: {"afterDeadline": "true"},
    InvoiceFilter.FORECAST: {"loadAfter30Days": "true"},
}


def _iso(d: date) -> str:
    """Dates are sent the way the web app sends them: ``Date.toISOString()`` of local midnight."""
    return f"{d.isoformat()}T00:00:00.000Z"


def _bool(v: bool) -> str:
    return "true" if v else "false"


def _filename(r: requests.Response) -> str | None:
    cd = r.headers.get("content-disposition") or ""
    m = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", cd, re.I) or re.search(r'filename="?([^";]+)"?', cd)
    return unquote(m.group(1).strip()) if m else None


class PgnigClient:
    """Logged-in session against ebok.myorlen.pl.

    >>> with PgnigClient("user@example.com", "secret") as c:
    ...     for inv in c.iter_invoices():
    ...         print(inv.number, inv.gross_amount, inv.is_paid)

    Methods that work on a meter point take an optional ``ppg`` (the PPG id from
    ``get_meter_points()``); it can be omitted when the account has a single one.
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        session: requests.Session | None = None,
        session_file: str | Path | None = None,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        user_agent: str = DEFAULT_USER_AGENT,
        device_id: str | None = None,
    ) -> None:
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.session.headers.setdefault("Accept", "application/json")
        self.session_file = Path(session_file).expanduser() if session_file else None
        self.device_id = device_id
        self.token: str | None = None
        self.token_expires: datetime | None = None
        self._meter_points: list[MeterPoint] | None = None
        if self.session_file and self.session_file.exists():
            self._load_session()
        if not self.device_id:
            # A stable id keeps the account's "devices" list from growing on every login.
            self.device_id = str(uuid.uuid4())

    # ---- context manager -----------------------------------------------------

    def __enter__(self) -> PgnigClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.save_session()
        self.session.close()

    # ---- session persistence -------------------------------------------------

    def _load_session(self) -> None:
        assert self.session_file is not None
        try:
            data = json.loads(self.session_file.read_text())
        except (OSError, ValueError):
            log.warning("ignoring unreadable session file %s", self.session_file)
            return
        if not isinstance(data, dict):
            return
        self.device_id = self.device_id or data.get("device_id")
        expires = parsers.to_datetime(data.get("expires"))
        if data.get("token") and (expires is None or expires > datetime.now(timezone.utc)):
            self.token = str(data["token"])
            self.token_expires = expires

    def save_session(self) -> None:
        """Write token + device id to ``session_file`` (if set) so the next run can skip logging in."""
        if not self.session_file:
            return
        data = {
            "token": self.token,
            "expires": self.token_expires.isoformat() if self.token_expires else None,
            "device_id": self.device_id,
        }
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.session_file.write_text(json.dumps(data))
        self.session_file.chmod(0o600)

    # ---- auth ----------------------------------------------------------------

    @property
    def logged_in(self) -> bool:
        return self.token is not None

    def login(self) -> None:
        """``POST /auth/login`` with e-mail (``Identificator``) and password (``AccessPin``)."""
        if not self.username or not self.password:
            raise AuthenticationError("username and password are required to log in")
        self.token = None
        self._meter_points = None
        r = self.session.post(
            f"{self.base_url}{EP_LOGIN}",
            params={"api-version": API_VERSION},
            json={
                "Identificator": self.username,
                "AccessPin": self.password,
                "DeviceType": "Web",
                "DeviceId": self.device_id,
                "DeviceName": DEVICE_NAME,
            },
            timeout=self.timeout,
        )
        if r.status_code in (401, 403):
            raise AuthenticationError(f"login failed: HTTP {r.status_code} (wrong e-mail or password?)")
        try:
            data = r.json()
        except ValueError as e:
            raise AuthenticationError(f"login failed: HTTP {r.status_code}, not JSON") from e
        code = data.get("Code") if isinstance(data, dict) else None
        if r.status_code >= 400 or code or not data.get("Token"):
            reason = LOGIN_ERRORS.get(code or 0) or data.get("EndUserMessage") or data.get("Message")
            raise AuthenticationError(f"login failed: {reason or f'code {code}, HTTP {r.status_code}'}")
        self.token = str(data["Token"])
        self.token_expires = parsers.to_datetime(data.get("DateExpirationUtc"))
        self.save_session()

    def logout(self) -> None:
        """End the server-side session and forget the token."""
        try:
            if self.token:
                self.session.post(
                    f"{self.base_url}{EP_LOGOUT}",
                    params={"api-version": API_VERSION},
                    json={},
                    headers={"AuthToken": self.token},
                    timeout=self.timeout,
                )
        finally:
            self.token = None
            self.token_expires = None
            self._meter_points = None
            self.save_session()

    def _ensure_login(self) -> None:
        if not self.token:
            self.login()

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """Authenticated request with one transparent re-login when the token was rejected (401)."""
        self._ensure_login()
        kwargs.setdefault("timeout", self.timeout)
        params = dict(kwargs.pop("params", None) or {})
        params["api-version"] = API_VERSION
        url = self.base_url + path
        extra_headers = kwargs.pop("headers", None) or {}
        for attempt in (1, 2):
            headers = {**extra_headers, "AuthToken": self.token or ""}
            r = self.session.request(method, url, params=params, headers=headers, **kwargs)
            if r.status_code == 401:
                if attempt == 1 and self.username and self.password:
                    log.info("token rejected, logging in again")
                    self.login()
                    continue
                raise AuthenticationError("token rejected and the session could not be re-established")
            if r.status_code >= 400:
                payload: Any
                try:
                    payload = r.json()
                except ValueError:
                    payload = r.text
                code = payload.get("Code") if isinstance(payload, dict) else None
                raise ApiError(f"{method} {path}: HTTP {r.status_code}", payload, code)
            return r
        raise AuthenticationError("session could not be re-established")  # pragma: no cover

    def _get(self, path: str, params: dict[str, Any] | None = None, *, lenient_code: bool = False) -> Any:
        r = self.request("GET", path, params=params)
        try:
            data = r.json()
        except ValueError as e:
            raise ApiError(f"{path}: expected JSON, got {r.headers.get('content-type')}") from e
        if isinstance(data, dict):
            expires = parsers.to_datetime(data.get("TokenExpireDateUtc"))
            if expires:
                self.token_expires = expires
            code = data.get("Code")
            if code and not (lenient_code and code == 1):
                msg = data.get("EndUserMessage") or data.get("Message") or f"code {code}"
                raise ApiError(f"{path}: {msg}", data, code)
        return data

    def _download(self, path: str, params: dict[str, Any], expect: str | None = None) -> DownloadedFile:
        r = self.request("GET", path, params=params)
        ctype = (r.headers.get("content-type") or "").split(";")[0].strip() or None
        if expect and ctype != expect:
            # e.g. text/plain "Brak podglądu PDF dla wybranej faktury." when no PDF is available
            raise ApiError(f"{path}: no file ({ctype}): {r.text[:200].strip()}", r.text)
        return DownloadedFile(filename=_filename(r), content_type=ctype, content=r.content)

    # ---- account -------------------------------------------------------------

    def get_user(self) -> User:
        """Logged-in user: name, e-mail, masked PESEL, balance and amount to pay."""
        # the web app treats Code 1 from this endpoint as success
        return parsers.parse_user(self._get(EP_USER, lenient_code=True))

    def get_related_accounts(self) -> list[RelatedAccount]:
        """Customer accounts linked to this login."""
        return parsers.parse_related_accounts(self._get(EP_RELATED_ACCOUNTS))

    def get_billing_summary(self) -> BillingSummary:
        """Headline status shown on the dashboard (``Paid``, ``ToPay``, ...)."""
        return parsers.parse_billing_summary(self._get(EP_BILLING_SUMMARY))

    def get_agreements(self, *, include_inactive: bool = False) -> list[Agreement]:
        """Supply agreements; ``include_inactive`` uses ``get-all-agreements``."""
        return parsers.parse_agreements(self._get(EP_ALL_AGREEMENTS if include_inactive else EP_AGREEMENTS))

    def get_agreement(self, number: str | None = None) -> Agreement:
        """Full agreement details (correspondence address, tariff, ...)."""
        agreements = self.get_agreements(include_inactive=True)
        if number is None:
            active = [a for a in agreements if a.active] or agreements
            if len(active) != 1:
                raise NotFoundError(
                    "pass number= one of " + ", ".join(a.number for a in agreements)
                    if agreements
                    else "no agreements on this account"
                )
            match = active[0]
        else:
            found = next((a for a in agreements if a.number == number), None)
            if found is None:
                raise NotFoundError(f"agreement {number} not found on this account")
            match = found
        data = self._get(
            EP_AGREEMENT_DETAILS, {"agreementNumber": match.number, "clientNumber": match.client_number}
        )
        return parsers.parse_agreement_details(data)

    def get_meter_points(self, refresh: bool = False) -> list[MeterPoint]:
        """Gas meter points (PPG) with the last reading."""
        if self._meter_points is None or refresh:
            self._meter_points = parsers.parse_meter_points(self._get(EP_PPG_LIST))
        return self._meter_points

    def get_meter_point(self, ppg: str | None = None) -> MeterPoint:
        points = self.get_meter_points()
        if ppg is None:
            if len(points) == 1:
                return points[0]
            if not points:
                raise NotFoundError("no meter points on this account")
            raise NotFoundError("several meter points, pass ppg= one of " + ", ".join(p.id for p in points))
        for p in points:
            if ppg in (p.id, p.meter_number, p.local_id):
                return p
        raise NotFoundError(f"meter point {ppg} not found on this account")

    # ---- invoices ------------------------------------------------------------

    def get_invoices(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        filter: InvoiceFilter | str = InvoiceFilter.ALL,
        date_from: date | None = None,
        date_to: date | None = None,
        agreement_number: str | None = None,
        client_number: str | None = None,
    ) -> InvoicePage:
        """One page of invoices, forecast instalments and interest notes, newest first."""
        params: dict[str, Any] = {"pageNumber": page, "pageSize": page_size}
        params.update(_INVOICE_FILTERS[InvoiceFilter(filter)])
        if date_from:
            params["dateFrom"] = _iso(date_from)
        if date_to:
            params["dateTo"] = _iso(date_to)
        if agreement_number:
            params["agreementNumber"] = agreement_number
        if client_number:
            params["clientNumber"] = client_number
        return parsers.parse_invoice_page(self._get(EP_INVOICES, params))

    def iter_invoices(self, *, page_size: int = 50, **filters: Any) -> Iterator[Invoice]:
        """All invoices matching the filters of :meth:`get_invoices`, following pages."""
        page = 1
        while True:
            result = self.get_invoices(page=page, page_size=page_size, **filters)
            yield from result.items
            if not result.has_more or not result.items:
                return
            page += 1

    def get_invoice(self, number: str) -> Invoice:
        """Details of one invoice or interest note (numbers starting with ``NO/``)."""
        if number.upper().startswith("NO/"):
            data = self._get(
                EP_INTEREST_NOTE_DETAILS, {"interestNoteNumber": number, "excludePdfCheck": "true"}
            )
            return parsers.parse_interest_note_details(data)
        data = self._get(EP_INVOICE_DETAILS, {"invoiceNumber": number, "excludePdfCheck": "true"})
        return parsers.parse_invoice_details(data)

    def download_invoice(self, invoice: Invoice | str) -> DownloadedFile:
        """The invoice PDF. Raises ``ApiError`` when the portal has no PDF for the document
        (common for interest notes)."""
        number = invoice.number if isinstance(invoice, Invoice) else invoice
        note = invoice.is_interest_note if isinstance(invoice, Invoice) else number.upper().startswith("NO/")
        if note:
            f = self._download(
                EP_INTEREST_NOTE_PDF, {"interestNoteNumber": number, "mode": "partial"}, "application/pdf"
            )
        else:
            f = self._download(
                EP_INVOICE_PDF, {"invoiceNumber": number, "mode": "partial"}, "application/pdf"
            )
        f.filename = re.sub(r"[^\w.-]+", "_", number) + ".pdf"
        return f

    # ---- payments & history --------------------------------------------------

    def get_payments(self) -> list[Payment]:
        """Payments booked on the account, newest first."""
        return parsers.parse_payments(self._get(EP_PAYMENTS))

    def get_account_history(self, *, page: int = 1, page_size: int = 30) -> list[HistoryEntry]:
        """eBOK action history (payments made, consents, agreement changes)."""
        return parsers.parse_history(self._get(EP_HISTORY, {"pageNumber": page, "pageSize": page_size}))

    # ---- readings & consumption ----------------------------------------------

    def get_readings(
        self,
        ppg: str | None = None,
        *,
        page: int = 1,
        page_size: int = 50,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> ReadingPage:
        """One page of meter readings of a meter point, newest first."""
        point = self.get_meter_point(ppg)
        params: dict[str, Any] = {"idPpg": point.id, "pageNumber": page, "pageSize": page_size}
        if date_from or date_to:
            params["dateFrom"] = _iso(date_from or date(2000, 1, 1))
            params["dateTo"] = _iso(date_to or date.today())
        else:
            params["ignoreStartDate"] = "true"
        return parsers.parse_reading_page(self._get(EP_READINGS, params))

    def iter_readings(
        self, ppg: str | None = None, *, page_size: int = 50, **filters: Any
    ) -> Iterator[Reading]:
        page = 1
        while True:
            result = self.get_readings(ppg, page=page, page_size=page_size, **filters)
            yield from result.items
            if not result.has_more or not result.items:
                return
            page += 1

    def get_reading_dates(self, ppg: str | None = None) -> list[date]:
        """Dates on which readings exist for a meter point."""
        point = self.get_meter_point(ppg)
        return parsers.parse_reading_dates(self._get(EP_READING_DATES, {"idPpg": point.id}))

    def export_readings(self, ppg: str | None = None) -> DownloadedFile:
        """The portal's Excel export of the reading history."""
        point = self.get_meter_point(ppg)
        return self._download(EP_READINGS_FILE, {"ppgIds": point.id})

    def get_monthly_consumption(self, ppg: str | None = None, *, months: int = 24) -> list[ConsumptionEntry]:
        """Consumption per settlement period (the "monthly" chart), oldest first."""
        point = self.get_meter_point(ppg)
        data = self._get(EP_MONTHLY, {"ppgIds": point.id, "pageNumber": 1, "pageSize": months})
        return parsers.parse_monthly_consumption(data)

    def get_yearly_consumption(self, ppg: str | None = None) -> YearlyConsumption:
        """This year vs previous year consumption."""
        point = self.get_meter_point(ppg)
        return parsers.parse_yearly_consumption(self._get(EP_YEARLY, {"ppgIds": point.id}))

    # ---- messages ------------------------------------------------------------

    def get_notifications(self) -> list[Notification]:
        """In-app notifications (new invoices, payment reminders, ...)."""
        return parsers.parse_notifications(self._get(EP_NOTIFICATIONS))

    def get_unread_count(self) -> int:
        return int(self._get(EP_UNREAD).get("UnreadedCount") or 0)

    def get_email_settings(self) -> EmailSettings:
        """Which e-mail notifications are enabled."""
        return parsers.parse_email_settings(self._get(EP_EMAIL_SETTINGS))

    def get_contact_history(self, *, page: int = 1, page_size: int = 20) -> list[ContactMessage]:
        """Messages sent through the contact form and their status."""
        items, _ = parsers.parse_contact_history(
            self._get(EP_CONTACT_HISTORY, {"pageIndex": page, "pageSize": page_size})
        )
        return items

    def iter_contact_history(self, *, page_size: int = 20) -> Iterator[ContactMessage]:
        page = 1
        while True:
            data = self._get(EP_CONTACT_HISTORY, {"pageIndex": page, "pageSize": page_size})
            items, more = parsers.parse_contact_history(data)
            yield from items
            if not more or not items:
                return
            page += 1
