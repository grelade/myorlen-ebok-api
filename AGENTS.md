# AGENTS.md

Guidance for coding agents working on this repository.

## What this is

`myorlen-ebok-api`: an unofficial Python SDK + CLI for the myORLEN gas eBOK
(https://ebok.myorlen.pl; previously PGNiG eBOK at ebok.pgnig.pl). The portal is a React SPA over a JSON API
on the same host; the SDK logs in with e-mail + password, keeps the returned token and calls
the same endpoints. **API.md is the endpoint reference**: read it before touching the client,
and update it whenever you learn something new about the site.

## Layout

```
src/myorlen_ebok_api/
  client.py      MyorlenClient: login, token handling, one method per feature (I/O only)
  parsers.py     pure functions JSON -> models; all field names of the API live here
  models.py      dataclasses (Decimal money, date dates), InvoiceFilter enum, to_jsonable()
  exceptions.py  MyorlenError > AuthenticationError | ApiError | ParseError | NotFoundError
  cli.py         `myorlen-ebok-api` argparse CLI, JSON on stdout
tests/
  fixtures/      ANONYMISED captures of real API responses
  test_parsers.py  parsers against fixtures
  test_client.py   client flows with HTTP mocked by `responses` (asserts request params too)
  test_cli.py      CLI end to end with mocked HTTP
  test_live.py     read-only checks against the real site, skipped unless MYORLEN_LIVE=1
```

## Commands

```bash
uv sync                                   # install (uses uv.lock)
uv run pytest                             # offline test suite, must stay green
uv run ruff check . && uv run ruff format --check .
uv run mypy                               # strict mode on src/
MYORLEN_LIVE=1 uv run pytest -m live        # needs MYORLEN_USER / MYORLEN_PASS (env or .env)
uv run myorlen-ebok-api --help              # CLI
```

Add dependencies with `uv add` / `uv add --dev` so `uv.lock` stays in sync. CI runs ruff,
mypy and pytest on Python 3.10–3.13 (`.github/workflows/ci.yml`).

## How a feature works (pattern to follow)

1. Find the route name in the web bundle (`https://ebok.myorlen.pl/static/js/main.js`): the
   route table is `var H={auth:{…},crm:{…}}`, call sites look like
   `Ct.getData("get_invoices_v2",{pageNumber:1,pageSize:12})` or `Ct.get("crm.get_ppg_list")`.
2. Call it through `MyorlenClient._get()` (adds `api-version=3.0` and the `AuthToken` header,
   re-logs in once on 401, raises `ApiError` on a non-zero `Code`) or `_download()` for files.
3. Parse with a pure function in `parsers.py` into a dataclass from `models.py`.

Keep I/O in `client.py` and parsing in `parsers.py`. New parsers get a fixture + test in
`test_parsers.py`; new client methods get a `responses` test that also asserts the query sent
(see existing tests).

## Site quirks worth knowing

- Every call needs `api-version=3.0`; the token goes in the `AuthToken` header, not a cookie.
- Wrong credentials give `403` with an empty body, not a JSON error.
- The token expires after about an hour (sliding, see `TokenExpireDateUtc` in every answer);
  the SDK caches it in the session file with a stable `DeviceId`.
- `get-user-data` may answer `Code: 1` on success.
- `get-invoices-v2` rejects `type=` with 400; use the boolean filters (API.md).
- `PdfExists` in invoice lists is always false; ask the PDF endpoint directly. Interest-note PDFs
  often come back as `text/plain` "Brak podglądu PDF…" instead of a PDF.
- `get-interest-note-details` uses different field names than invoices (`DocumentNumber`,
  `DateCreated`, `DatePaymentDeadline`).

## Releasing

Releases go to PyPI from GitHub Actions (`.github/workflows/release.yml`) via trusted
publishing; there is no token to manage.

1. Bump the version: `uv version --bump patch` (or `minor` / `major`); this updates `pyproject.toml` and `uv.lock`.
2. Commit, then tag and push: `git tag v$(uv version --short) && git push && git push --tags`.
3. The workflow runs CI, checks the tag matches the version, builds and smoke-tests the wheel,
   publishes to https://pypi.org/project/myorlen-ebok-api/ and creates a GitHub release with the files attached.

PyPI versions can never be re-uploaded, so a broken release needs a new version number.

## Safety rules

- **Never commit personal data.** `.env` holds real credentials and is gitignored. Fixtures must
  be anonymised: replace names, addresses, client / agreement / PPG / meter numbers, e-mails,
  phone, PESEL, IBANs, document numbers, UUIDs and tokens before saving into `tests/fixtures/`.
  Grep the fixtures for the real values before committing.
- Live exploration is read-only. Do not call payment endpoints (`pay-for-*`), reading
  submission (`add-ppg-reading*`, `cancel-reading`), contact forms, agreement changes, e-invoice
  toggles or account settings. If the SDK ever exposes a write endpoint, test it with mocks only.
- Keep request volume low when exploring (one login, reuse the token).
