# myorlen-ebok-api

Unofficial Python SDK and command-line client for the **myORLEN eBOK**
([ebok.myorlen.pl](https://ebok.myorlen.pl)), the customer portal of the Polish gas retailer myORLEN.

> **Previous name: PGNiG eBOK.** The portal used to be the eBOK of PGNiG Obrót Detaliczny at
> `ebok.pgnig.pl`; after the rebranding to myORLEN that address redirects to `ebok.myorlen.pl`.
> Existing PGNiG eBOK logins work unchanged.

It logs in with your eBOK e-mail and password and gives typed access to what the portal shows:

- user data, balance and amount to pay, linked customer accounts
- supply agreements with tariff, address, IBAN, collection points; agreement details
- invoices, forecast instalments and interest notes (filters, paging), invoice details, **PDF downloads**
- payments booked on the account, eBOK action history
- gas meter points (PPG) with the last reading; reading history, Excel export
- consumption per settlement period and year-over-year comparison
- notifications, contact-form history, e-mail notification settings

> Not affiliated with PGNiG or ORLEN. The portal has no public API; this library calls the
> same JSON endpoints the web app uses and can break when they change.
> See [API.md](API.md) for the reverse-engineered endpoint reference.

## Install

```bash
pip install myorlen-ebok-api        # or: uv add myorlen-ebok-api
```

Latest unreleased code: `pip install git+https://github.com/grelade/myorlen-ebok-api`.

Requires Python 3.10+.

## Command line

```bash
export MYORLEN_USER=you@example.com MYORLEN_PASS='…'     # or put them in ./.env (PGNIG_USER / PGNIG_PASS also work)
uvx myorlen-ebok-api balance
```

| Command | Output |
|---|---|
| `user`, `balance`, `accounts` | user data, balance / amount to pay / payment status, linked accounts |
| `agreements [--all]` / `agreement [NUMBER]` | supply agreements / details of one |
| `meter-points` | meter points (PPG) with the last reading |
| `invoices [--from D] [--to D] [--filter all\|unpaid\|overdue\|forecast] [--agreement N] [--limit N]` | invoices |
| `invoice NUMBER` | invoice or interest-note details |
| `pdf NUMBER [--out DIR_OR_FILE]` | save an invoice PDF |
| `payments`, `history [--limit N]` | payments, eBOK action history |
| `readings [--from D] [--to D] [--xlsx PATH]` | meter readings (m³) or the Excel export |
| `monthly [--months N]`, `yearly` | consumption charts |
| `notifications`, `contacts`, `email-settings` | messages and settings |

Output is JSON (amounts are strings to keep `Decimal` precision). Global options: `--ppg ID`
(needed only for accounts with several meter points) and `--session-file PATH` (default
`~/.cache/myorlen-ebok-api/session.json`; the token is reused so repeated runs don't log in again).

## Library

```python
from myorlen_ebok_api import MyorlenClient

with MyorlenClient("you@example.com", "secret", session_file="~/.cache/myorlen-ebok-api/session.json") as c:
    user = c.get_user()
    print(user.balance, user.amount_to_pay)

    for inv in c.iter_invoices(filter="unpaid"):
        print(inv.number, inv.gross_amount, inv.due_date)

    latest = next(c.iter_invoices())
    pdf = c.download_invoice(latest)  # DownloadedFile(filename, content_type, content)
    open(pdf.filename, "wb").write(pdf.content)

    for r in c.iter_readings():
        print(r.date, r.value, r.consumption, "m³")
```

All methods: `get_user`, `get_related_accounts`, `get_billing_summary`, `get_agreements`,
`get_agreement`, `get_meter_points`, `get_meter_point`, `get_invoices`, `iter_invoices`,
`get_invoice`, `download_invoice`, `get_payments`, `get_account_history`, `get_readings`,
`iter_readings`, `get_reading_dates`, `export_readings`, `get_monthly_consumption`,
`get_yearly_consumption`, `get_notifications`, `get_unread_count`, `get_email_settings`,
`get_contact_history`, `iter_contact_history`; session: `login`, `logout`, `save_session`.

Errors derive from `myorlen_ebok_api.MyorlenError` (`AuthenticationError`, `ApiError`, `ParseError`,
`NotFoundError`).

## Development

```bash
uv sync                          # creates .venv with dev tools
uv run pytest                    # offline tests (HTTP mocked, anonymised fixtures)
uv run ruff check . && uv run ruff format --check . && uv run mypy
MYORLEN_LIVE=1 uv run pytest -m live   # read-only smoke tests against the real site (.env credentials)
```

See [AGENTS.md](AGENTS.md) for the project layout and conventions.

## License

MIT
