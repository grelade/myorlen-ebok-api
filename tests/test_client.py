from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from pgnig_ebok_api import (
    ApiError,
    AuthenticationError,
    InvoiceFilter,
    NotFoundError,
    PgnigClient,
)

from .conftest import AGREEMENT, BASE, CLIENT, PPG, TOKEN, add_fixture, add_json, fixture_json, login_ok


def query(call: responses.Call) -> dict[str, str]:
    assert call.request.url is not None
    return {k: v[0] for k, v in parse_qs(urlparse(call.request.url).query).items()}


# ---- auth --------------------------------------------------------------------


def test_login_sends_credentials_and_stores_token(mocked: responses.RequestsMock, tmp_path: Path) -> None:
    login_ok(mocked, "tok-1")
    sf = tmp_path / "s.json"
    c = PgnigClient("u@example.com", "pw", session_file=sf, device_id="dev-1")
    c.login()
    call = mocked.calls[0]
    assert query(call)["api-version"] == "3.0"
    body = json.loads(call.request.body or b"{}")
    assert body == {
        "Identificator": "u@example.com",
        "AccessPin": "pw",
        "DeviceType": "Web",
        "DeviceId": "dev-1",
        "DeviceName": "pgnig-ebok-api",
    }
    assert c.token == "tok-1"
    saved = json.loads(sf.read_text())
    assert saved["token"] == "tok-1" and saved["device_id"] == "dev-1"
    assert sf.stat().st_mode & 0o777 == 0o600


def test_session_file_reused(mocked: responses.RequestsMock, tmp_path: Path) -> None:
    sf = tmp_path / "s.json"
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    sf.write_text(json.dumps({"token": "cached", "expires": future, "device_id": "dev-x"}))
    add_fixture(mocked, "/crm/get-billing-summary", "billing_summary")
    c = PgnigClient("u", "p", session_file=sf)
    assert c.token == "cached" and c.device_id == "dev-x"
    c.get_billing_summary()
    assert len(mocked.calls) == 1
    assert mocked.calls[0].request.headers["AuthToken"] == "cached"


def test_expired_session_file_ignored(tmp_path: Path) -> None:
    sf = tmp_path / "s.json"
    sf.write_text(json.dumps({"token": "old", "expires": "2000-01-01T00:00:00Z", "device_id": "dev-x"}))
    c = PgnigClient("u", "p", session_file=sf)
    assert c.token is None and c.device_id == "dev-x"
    sf.write_text("not json")
    assert PgnigClient("u", "p", session_file=sf).token is None


def test_login_wrong_credentials(mocked: responses.RequestsMock) -> None:
    mocked.add("POST", BASE + "/auth/login", status=403, body="")
    with pytest.raises(AuthenticationError, match="403"):
        PgnigClient("u", "bad").login()


def test_login_error_code(mocked: responses.RequestsMock) -> None:
    add_json(mocked, "/auth/login", {"Code": 1025, "Token": None}, method="POST")
    with pytest.raises(AuthenticationError, match="blocked"):
        PgnigClient("u", "p").login()


def test_login_requires_credentials() -> None:
    with pytest.raises(AuthenticationError):
        PgnigClient().login()


def test_relogin_on_401(mocked: responses.RequestsMock) -> None:
    c = PgnigClient("u", "p")
    c.token = "stale"
    mocked.add("GET", BASE + "/crm/get-billing-summary", status=401, json={"Message": "denied"})
    login_ok(mocked, "fresh")
    add_fixture(mocked, "/crm/get-billing-summary", "billing_summary")
    assert c.get_billing_summary().status == "Paid"
    assert c.token == "fresh"
    assert mocked.calls[-1].request.headers["AuthToken"] == "fresh"


def test_401_without_credentials(mocked: responses.RequestsMock) -> None:
    c = PgnigClient()
    c.token = "stale"
    mocked.add("GET", BASE + "/crm/get-billing-summary", status=401)
    with pytest.raises(AuthenticationError):
        c.get_billing_summary()


def test_api_errors(client: PgnigClient, mocked: responses.RequestsMock) -> None:
    add_json(mocked, "/crm/get-invoices-v2", {"Code": 1, "Message": "bad"}, status=400)
    with pytest.raises(ApiError) as e:
        client.get_invoices()
    assert e.value.code == 1
    add_json(mocked, "/crm/get-client-payments", {"Code": 7, "EndUserMessage": "nope"})
    with pytest.raises(ApiError, match="nope"):
        client.get_payments()
    mocked.add("GET", BASE + "/crm/get-refunds", body="<html>", content_type="text/html")
    with pytest.raises(ApiError, match="expected JSON"):
        client._get("/crm/get-refunds")


def test_user_data_code_1_is_ok(client: PgnigClient, mocked: responses.RequestsMock) -> None:
    data = fixture_json("user_data")
    data["Code"] = 1
    add_json(mocked, "/crm/get-user-data", data)
    assert client.get_user().first_name == "Jan"


def test_logout(client: PgnigClient, mocked: responses.RequestsMock) -> None:
    add_json(mocked, "/auth/logout", {"Code": 0}, method="POST")
    client.logout()
    assert mocked.calls[0].request.headers["AuthToken"] == TOKEN
    assert client.token is None


# ---- account -----------------------------------------------------------------


def test_agreements(client: PgnigClient, mocked: responses.RequestsMock) -> None:
    add_fixture(mocked, "/crm/get-agreements", "agreements")
    add_fixture(mocked, "/crm/get-all-agreements", "agreements")
    assert client.get_agreements()[0].number == AGREEMENT
    client.get_agreements(include_inactive=True)
    assert mocked.calls[1].request.url is not None and "get-all-agreements" in mocked.calls[1].request.url


def test_agreement_details(client: PgnigClient, mocked: responses.RequestsMock) -> None:
    add_fixture(mocked, "/crm/get-all-agreements", "agreements")
    add_fixture(mocked, "/crm/get-agreement-details", "agreement_details")
    a = client.get_agreement()
    assert a.correspondence_address is not None
    assert query(mocked.calls[-1]) == {
        "agreementNumber": AGREEMENT,
        "clientNumber": CLIENT,
        "api-version": "3.0",
    }
    with pytest.raises(NotFoundError):
        client.get_agreement("nope")


def test_meter_point_selection(client: PgnigClient, mocked: responses.RequestsMock, ppg_list: None) -> None:
    assert client.get_meter_point().id == PPG
    assert client.get_meter_point("1111111").id == PPG  # local id works too
    with pytest.raises(NotFoundError):
        client.get_meter_point("x")
    assert len(mocked.calls) == 1  # cached
    data = fixture_json("ppg_list")
    data["PpgList"].append({**data["PpgList"][0], "IdPPG": "other"})
    client._meter_points = None
    mocked.replace("GET", BASE + "/crm/get-ppg-list", json=data)
    with pytest.raises(NotFoundError, match="several"):
        client.get_meter_point()


def test_user_accounts_summary(client: PgnigClient, mocked: responses.RequestsMock) -> None:
    add_fixture(mocked, "/crm/get-user-data", "user_data")
    add_fixture(mocked, "/auth/get-related-accounts", "related")
    add_fixture(mocked, "/crm/get-billing-summary", "billing_summary")
    assert client.get_user().email == "jan.kowalski@example.com"
    assert client.get_related_accounts()[0].current
    assert client.get_billing_summary().status == "Paid"
    for call in mocked.calls:
        assert call.request.headers["AuthToken"] == TOKEN


# ---- invoices ----------------------------------------------------------------


def test_get_invoices_params(client: PgnigClient, mocked: responses.RequestsMock) -> None:
    add_fixture(mocked, "/crm/get-invoices-v2", "invoices_p2")
    client.get_invoices(
        page=2,
        page_size=10,
        filter=InvoiceFilter.UNPAID,
        date_from=date(2025, 1, 1),
        date_to=date(2025, 12, 31),
        agreement_number=AGREEMENT,
        client_number=CLIENT,
    )
    assert query(mocked.calls[0]) == {
        "pageNumber": "2",
        "pageSize": "10",
        "paid": "false",
        "dateFrom": "2025-01-01T00:00:00.000Z",
        "dateTo": "2025-12-31T00:00:00.000Z",
        "agreementNumber": AGREEMENT,
        "clientNumber": CLIENT,
        "api-version": "3.0",
    }
    client.get_invoices(filter="overdue")
    assert query(mocked.calls[1])["afterDeadline"] == "true"


def test_iter_invoices_follows_pages(client: PgnigClient, mocked: responses.RequestsMock) -> None:
    add_fixture(mocked, "/crm/get-invoices-v2", "invoices")
    add_fixture(mocked, "/crm/get-invoices-v2", "invoices_p2")
    invoices = list(client.iter_invoices(page_size=12))
    assert len(invoices) == 14
    assert [query(c)["pageNumber"] for c in mocked.calls] == ["1", "2"]


def test_get_invoice_routes_by_number(client: PgnigClient, mocked: responses.RequestsMock) -> None:
    add_fixture(mocked, "/crm/get-invoice-details", "invoice_details")
    add_fixture(mocked, "/crm/get-interest-note-details", "note_details")
    assert client.get_invoice("P/1234567/0001/26").kind == "R"
    assert query(mocked.calls[0])["invoiceNumber"] == "P/1234567/0001/26"
    assert client.get_invoice("NO/1234567/000001/26").is_interest_note
    assert query(mocked.calls[1])["interestNoteNumber"] == "NO/1234567/000001/26"


def test_download_invoice(client: PgnigClient, mocked: responses.RequestsMock) -> None:
    mocked.add(
        "GET",
        BASE + "/crm/get-invoice-pdf",
        body=b"%PDF-1.4 test",
        content_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="p/1234567/0001/26.pdf"'},
    )
    f = client.download_invoice("P/1234567/0001/26")
    assert f.content.startswith(b"%PDF") and f.filename == "P_1234567_0001_26.pdf"
    assert query(mocked.calls[0]) == {
        "invoiceNumber": "P/1234567/0001/26",
        "mode": "partial",
        "api-version": "3.0",
    }
    assert f.to_dict()["size"] == len(b"%PDF-1.4 test")


def test_download_interest_note_without_pdf(client: PgnigClient, mocked: responses.RequestsMock) -> None:
    mocked.add(
        "GET",
        BASE + "/crm/get-interest-note-pdf",
        body="Brak podglądu PDF dla wybranej faktury.",
        content_type="text/plain; charset=utf-8",
    )
    with pytest.raises(ApiError, match="Brak podglądu"):
        client.download_invoice("NO/1234567/000001/26")


# ---- payments, history, messages ---------------------------------------------


def test_payments_history_messages(client: PgnigClient, mocked: responses.RequestsMock) -> None:
    add_fixture(mocked, "/crm/get-client-payments", "client_payments")
    add_fixture(mocked, "/crm/get-account-history", "account_history")
    add_fixture(mocked, "/notification/get-notifications", "notifications")
    add_fixture(mocked, "/notification/get-unreaded-count", "unread")
    add_fixture(mocked, "/notification/email-settings", "email_notif")
    add_fixture(mocked, "/contact/get-contact-history-v2", "contact_history")
    assert len(client.get_payments()) == 14
    assert client.get_account_history(page=2, page_size=5)
    assert query(mocked.calls[1])["pageNumber"] == "2" and query(mocked.calls[1])["pageSize"] == "5"
    assert len(client.get_notifications()) == 4
    assert client.get_unread_count() == 0
    assert client.get_email_settings().invoices
    assert client.get_contact_history() == []
    assert list(client.iter_contact_history()) == []
    assert query(mocked.calls[-1])["pageIndex"] == "1"


# ---- readings ----------------------------------------------------------------


def test_readings_params(client: PgnigClient, mocked: responses.RequestsMock, ppg_list: None) -> None:
    add_fixture(mocked, "/crm/get-all-ppg-readings-for-meter", "readings")
    assert len(list(client.iter_readings())) == 2
    q = query(mocked.calls[-1])
    assert q["idPpg"] == PPG and q["ignoreStartDate"] == "true" and q["pageNumber"] == "1"
    client.get_readings(date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
    q = query(mocked.calls[-1])
    assert q["dateFrom"] == "2025-01-01T00:00:00.000Z" and q["dateTo"] == "2025-12-31T00:00:00.000Z"
    assert "ignoreStartDate" not in q


def test_consumption_and_export(client: PgnigClient, mocked: responses.RequestsMock, ppg_list: None) -> None:
    add_fixture(mocked, "/crm/get-monthly-wear-chart-data", "monthly")
    add_fixture(mocked, "/crm/get-yearly-wear-chart-data", "yearly")
    add_fixture(mocked, "/crm/get-ppg-readings-dates", "reading_dates")
    mocked.add(
        "GET",
        BASE + "/crm/get-ppgs-readings-file",
        body=b"PK\x03\x04",
        content_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=Readings_2026_11_13.xlsx"},
    )
    assert len(client.get_monthly_consumption(months=12)) == 1
    assert query(mocked.calls[-1]) == {
        "ppgIds": PPG,
        "pageNumber": "1",
        "pageSize": "12",
        "api-version": "3.0",
    }
    assert client.get_yearly_consumption().this_year[0].year == "2026"
    assert client.get_reading_dates()[0] == date(2026, 10, 27)
    f = client.export_readings()
    assert f.filename == "Readings_2026_11_13.xlsx" and f.content.startswith(b"PK")
