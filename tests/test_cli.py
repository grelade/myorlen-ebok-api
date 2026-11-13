from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses

from pgnig_ebok_api import cli

from .conftest import AGREEMENT, BASE, PPG, add_fixture, login_ok


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.chdir(tmp_path)  # no stray .env
    monkeypatch.setenv("PGNIG_USER", "u@example.com")
    monkeypatch.setenv("PGNIG_PASS", "secret")
    return tmp_path


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, object]:
    code = cli.main(["--session-file", "", *argv])
    out = capsys.readouterr().out
    try:
        return code, json.loads(out)
    except ValueError:
        return code, out.strip()


def test_missing_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PGNIG_USER", raising=False)
    monkeypatch.delenv("PGNIG_PASS", raising=False)
    assert cli.main(["--session-file", "", "user"]) == 2


def test_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PGNIG_USER", raising=False)
    (tmp_path / ".env").write_text("# c\nPGNIG_USER='a@b.c'\nbad line\n")
    cli.load_dotenv(tmp_path / ".env")
    import os

    assert os.environ["PGNIG_USER"] == "a@b.c"
    monkeypatch.delenv("PGNIG_USER")


def test_balance_and_invoices(
    env: Path, mocked: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    login_ok(mocked)
    add_fixture(mocked, "/crm/get-user-data", "user_data")
    add_fixture(mocked, "/crm/get-billing-summary", "billing_summary")
    code, out = run(capsys, "balance")
    assert code == 0
    assert out == {"balance": "0.0", "amount_to_pay": "0.0", "status": "Paid", "value": None}

    add_fixture(mocked, "/crm/get-invoices-v2", "invoices")
    code, out = run(capsys, "invoices", "--limit", "2", "--agreement", AGREEMENT)
    assert code == 0 and isinstance(out, list) and len(out) == 2
    assert out[1]["gross_amount"] == "628.26"


def test_account_commands(
    env: Path, mocked: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    login_ok(mocked)
    add_fixture(mocked, "/crm/get-ppg-list", "ppg_list")
    add_fixture(mocked, "/crm/get-agreements", "agreements")
    add_fixture(mocked, "/crm/get-all-agreements", "agreements")
    add_fixture(mocked, "/crm/get-agreement-details", "agreement_details")
    add_fixture(mocked, "/auth/get-related-accounts", "related")
    add_fixture(mocked, "/crm/get-user-data", "user_data")
    add_fixture(mocked, "/crm/get-client-payments", "client_payments")
    add_fixture(mocked, "/crm/get-account-history", "account_history")
    add_fixture(mocked, "/notification/get-notifications", "notifications")
    add_fixture(mocked, "/notification/email-settings", "email_notif")
    add_fixture(mocked, "/contact/get-contact-history-v2", "contact_history")
    add_fixture(mocked, "/crm/get-invoice-details", "invoice_details")
    expectations = {
        ("meter-points",): lambda o: o[0]["id"] == PPG,
        ("agreements", "--all"): lambda o: o[0]["number"] == AGREEMENT,
        ("agreement",): lambda o: o["owner"] is True,
        ("accounts",): lambda o: o[0]["current"],
        ("user",): lambda o: o["first_name"] == "Jan",
        ("payments",): lambda o: len(o) == 14,
        ("history", "--limit", "5"): lambda o: isinstance(o, list),
        ("notifications",): lambda o: len(o) == 4,
        ("email-settings",): lambda o: o == {"system": True, "invoices": True},
        ("contacts",): lambda o: o == [],
        ("invoice", "P/1234567/0001/26"): lambda o: o["kind"] == "R",
    }
    for argv, check in expectations.items():
        code, out = run(capsys, *argv)
        assert code == 0, argv
        assert check(out), argv


def test_readings_commands(
    env: Path, mocked: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    login_ok(mocked)
    add_fixture(mocked, "/crm/get-ppg-list", "ppg_list")
    add_fixture(mocked, "/crm/get-all-ppg-readings-for-meter", "readings")
    add_fixture(mocked, "/crm/get-monthly-wear-chart-data", "monthly")
    add_fixture(mocked, "/crm/get-yearly-wear-chart-data", "yearly")
    mocked.add(
        "GET", BASE + "/crm/get-ppgs-readings-file", body=b"PK", content_type="application/octet-stream"
    )
    code, out = run(capsys, "readings", "--from", "2025-01-01")
    assert code == 0 and isinstance(out, list) and out[0]["value"] == "2238.0"
    code, out = run(capsys, "monthly", "--months", "6")
    assert code == 0 and isinstance(out, list) and out[0]["consumption"] == "487.0"
    code, out = run(capsys, "yearly")
    assert code == 0 and isinstance(out, dict) and out["comparison_percent"] == "15.0"
    code, out = run(capsys, "readings", "--xlsx", "r.xlsx")
    assert code == 0 and (env / "r.xlsx").read_bytes() == b"PK"


def test_pdf(env: Path, mocked: responses.RequestsMock, capsys: pytest.CaptureFixture[str]) -> None:
    login_ok(mocked)
    mocked.add("GET", BASE + "/crm/get-invoice-pdf", body=b"%PDF-1.4", content_type="application/pdf")
    code, _ = run(capsys, "pdf", "P/1234567/0001/26", "--out", "pdfs/")
    assert code == 0
    assert (env / "pdfs" / "P_1234567_0001_26.pdf").read_bytes() == b"%PDF-1.4"


def test_error_exit_code(
    env: Path, mocked: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mocked.add("POST", BASE + "/auth/login", status=403)
    assert cli.main(["--session-file", "", "user"]) == 1
    assert "login failed" in capsys.readouterr().err
