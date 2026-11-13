"""``pgnig-ebok-api`` command line interface. Prints JSON to stdout; files are written to disk.

Credentials come from ``PGNIG_USER`` / ``PGNIG_PASS`` (environment or a ``.env`` file in
the current directory). The session token is cached in ``~/.cache/pgnig-ebok-api/session.json``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from . import __version__
from .client import PgnigClient
from .exceptions import PgnigError
from .models import DownloadedFile, InvoiceFilter, to_jsonable

DEFAULT_SESSION_FILE = Path("~/.cache/pgnig-ebok-api/session.json")


def load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE lines, existing environment wins."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _print(data: Any) -> None:
    json.dump(to_jsonable(data), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def _save(file: DownloadedFile, out: str) -> Path:
    dest = Path(out)
    if dest.is_dir() or out.endswith(("/", os.sep)):
        dest.mkdir(parents=True, exist_ok=True)
        dest = dest / (file.filename or "download.bin")
    dest.write_bytes(file.content)
    return dest


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="pgnig-ebok-api", description="Unofficial PGNiG / myORLEN eBOK (ebok.myorlen.pl) client"
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--ppg", help="meter point id (needed only when the account has several)")
    ap.add_argument(
        "--session-file",
        default=os.environ.get("PGNIG_SESSION_FILE", str(DEFAULT_SESSION_FILE)),
        help="where to cache the session token ('' disables)",
    )
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    def dates(p: argparse.ArgumentParser) -> None:
        p.add_argument("--from", dest="date_from", type=date.fromisoformat, help="YYYY-MM-DD")
        p.add_argument("--to", dest="date_to", type=date.fromisoformat, help="YYYY-MM-DD")

    sub.add_parser("user", help="logged-in user with balance and amount to pay")
    sub.add_parser("balance", help="balance, amount to pay and dashboard payment status")
    sub.add_parser("accounts", help="customer accounts linked to the login")

    p = sub.add_parser("agreements", help="supply agreements")
    p.add_argument("--all", action="store_true", help="include inactive agreements")
    p = sub.add_parser("agreement", help="details of one agreement")
    p.add_argument("number", nargs="?", help="agreement number (default: the only active one)")

    sub.add_parser("meter-points", help="gas meter points (PPG) with the last reading")

    p = sub.add_parser("invoices", help="invoices, forecast instalments and interest notes")
    dates(p)
    p.add_argument("--filter", choices=[f.value for f in InvoiceFilter], default="all")
    p.add_argument("--agreement", help="agreement number")
    p.add_argument("--limit", type=int, default=0, help="max rows (0 = all)")
    p = sub.add_parser("invoice", help="details of one invoice / interest note")
    p.add_argument("number", help="e.g. P/1234567/0001/26 or NO/1234567/000001/26")
    p = sub.add_parser("pdf", help="download an invoice PDF")
    p.add_argument("number")
    p.add_argument("--out", default=".", help="file or directory (default: current directory)")

    sub.add_parser("payments", help="payments booked on the account")
    p = sub.add_parser("history", help="eBOK action history")
    p.add_argument("--limit", type=int, default=30)

    p = sub.add_parser("readings", help="meter readings (m³)")
    dates(p)
    p.add_argument("--xlsx", metavar="PATH", help="save the portal's Excel export instead of printing")
    p = sub.add_parser("monthly", help="consumption per settlement period")
    p.add_argument("--months", type=int, default=24)
    sub.add_parser("yearly", help="this year vs previous year consumption")

    sub.add_parser("notifications", help="in-app notifications")
    sub.add_parser("contacts", help="contact form history")
    sub.add_parser("email-settings", help="e-mail notification settings")
    return ap


def run(args: argparse.Namespace, client: PgnigClient) -> None:
    ppg = args.ppg
    cmd = args.cmd
    if cmd == "user":
        _print(client.get_user())
    elif cmd == "balance":
        user = client.get_user()
        summary = client.get_billing_summary()
        _print({"balance": user.balance, "amount_to_pay": user.amount_to_pay, **summary.to_dict()})
    elif cmd == "accounts":
        _print(client.get_related_accounts())
    elif cmd == "agreements":
        _print(client.get_agreements(include_inactive=args.all))
    elif cmd == "agreement":
        _print(client.get_agreement(args.number))
    elif cmd == "meter-points":
        _print(client.get_meter_points())
    elif cmd == "invoices":
        invoices = []
        for inv in client.iter_invoices(
            filter=args.filter,
            date_from=args.date_from,
            date_to=args.date_to,
            agreement_number=args.agreement,
        ):
            invoices.append(inv)
            if args.limit and len(invoices) >= args.limit:
                break
        _print(invoices)
    elif cmd == "invoice":
        _print(client.get_invoice(args.number))
    elif cmd == "pdf":
        print(_save(client.download_invoice(args.number), args.out))
    elif cmd == "payments":
        _print(client.get_payments())
    elif cmd == "history":
        _print(client.get_account_history(page_size=args.limit))
    elif cmd == "readings":
        if args.xlsx:
            print(_save(client.export_readings(ppg), args.xlsx))
        else:
            _print(list(client.iter_readings(ppg, date_from=args.date_from, date_to=args.date_to)))
    elif cmd == "monthly":
        _print(client.get_monthly_consumption(ppg, months=args.months))
    elif cmd == "yearly":
        _print(client.get_yearly_consumption(ppg))
    elif cmd == "notifications":
        _print(client.get_notifications())
    elif cmd == "contacts":
        _print(list(client.iter_contact_history()))
    elif cmd == "email-settings":
        _print(client.get_email_settings())
    else:  # pragma: no cover - argparse rejects unknown commands
        raise SystemExit(f"unknown command {cmd}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(Path.cwd() / ".env")
    user, password = os.environ.get("PGNIG_USER"), os.environ.get("PGNIG_PASS")
    session_file = args.session_file or None
    if not (user and password) and not (session_file and Path(session_file).expanduser().exists()):
        print("error: set PGNIG_USER and PGNIG_PASS (environment or .env)", file=sys.stderr)
        return 2
    try:
        with PgnigClient(user, password, session_file=session_file) as client:
            run(args, client)
    except PgnigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
