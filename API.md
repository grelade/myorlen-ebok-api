# myORLEN eBOK (ebok.myorlen.pl, formerly PGNiG eBOK): reverse-engineered API reference

Mapped in November 2026 against a live household account (one gas agreement, tariff W-2.1)
and the web app bundle (`/static/js/main.js?v=1.1646`). Unofficial: the operator can change
any of this without notice. Implemented in `src/myorlen_ebok_api/client.py` (HTTP) and
`src/myorlen_ebok_api/parsers.py` (JSON parsing). All example values below are fake.

> **Host.** `https://ebok.pgnig.pl/` now redirects (301) to `https://ebok.myorlen.pl/`.
> Only the new host is used.

## Architecture

- `ebok.myorlen.pl` serves a **React SPA**; its JSON API lives on the same origin under
  `/auth/…`, `/crm/…`, `/notification/…`, `/contact/…`, `/agreements/…`, `/cms/…`.
  The bundle has the full route table (`var H={auth:{login:"/auth/login",…},crm:{…}}`).
- Every request carries the query parameter **`api-version=3.0`**.
- Authenticated requests send the token in the **`AuthToken`** request header (no cookies needed).
- JSON is PascalCase. Every answer has an envelope:
  `Code` (0 = OK), `Message`, `DisplayToEndUser`, `EndUserMessage`, `TokenExpireDate`,
  `TokenExpireDateUtc` (sliding token expiry), `ConfigUpdateDateUtc`.
  `crm/get-user-data` can answer `Code: 1` on success (the web app treats it as 0).
- Timestamps: `2026-10-27T00:00:00.000000Z`. Query dates are sent as `Date.toISOString()`,
  e.g. `2025-01-01T00:00:00.000Z`. Amounts are JSON numbers (PLN), volumes in m³, energy in kWh.
- Missing / invalid token → `401 {"Message": "Authorization has been denied for this request."}`.
- Bad request parameters → `400` with `Code: 1`.

## Authentication

`POST /auth/login?api-version=3.0`, JSON body:

```json
{"Identificator": "you@example.com", "AccessPin": "password",
 "DeviceType": "Web", "DeviceId": "<uuid>", "DeviceName": "…"}
```

Success → `200` with `Token`, `DateExpirationUtc` (≈1 h), `AutomaticLoginToken` (for
`/auth/login-automatic-token`, "remember me"), flags (`NewUser`, `ForceChangePasswordByInvalidPolicy`, …).
Wrong credentials → `403` with an empty body. Other failures carry `Code`: 1011 unauthorised
device, 1015 user not found, 1018 not activated, 1025 temporarily blocked (5 minutes).
No captcha on this endpoint (the site has a reCAPTCHA key, used by other forms).

`DeviceId` shows up in the account's device list (`/auth/get-devices`); the SDK keeps it stable
in the session file. Logout: `POST /auth/logout` with `{}` and the `AuthToken` header.

The site also has an OpenID flow (`/auth/oid/init-login` → `RedirectUrl`), used for accounts
migrated to the shared ORLEN identity; the SDK uses the classic login above.

## Endpoints (all `GET`, all need `AuthToken`)

### Account

| Endpoint | Params | Response |
|---|---|---|
| `/crm/get-user-data` | – | `Email`, `FirstName`, `LastName`, `Pesel` (masked `800********`), `Nip`, `Saldo`, `AmountToPay`, `Billing`, `HasPrepaid`, `Acceptances[]` (consent texts), … |
| `/auth/get-related-accounts` | – | `RelatedAccounts[]`: `PublicId`, `ClientNumber`, `Current`, `ClientName`, `Pesel` |
| `/crm/get-other-accounts` | – | `Results[]`: other eBOK logins for the same PESEL (masked e-mail) |
| `/crm/get-billing-summary` | – | `{Status: "Paid", Value: null}` (dashboard headline) |
| `/crm/get-agreements` | – | `Agreements[]` (active) |
| `/crm/get-all-agreements` | – | `Agreements[]` incl. inactive |
| `/crm/get-agreement-details` | `agreementNumber`, `clientNumber` | `{Agreement: {...}}`, superset of the list item (+ `AddressForCorrespondence`, `FirstName`, `LastName`, `IsOwner`, `NotExpiredChanges`) |
| `/crm/get-ppg-list` | – | `PpgList[]`: `IdPPG`, `MeterNumber`, `Address`, `ReadingDateUtc`, `ReadingValue`, `ContractNumber`, `ClientNumber`, `Tariff`, `IdLocal`, `HasHistory`, `AddReadingMode`, … |

Agreement item: `Type` (`PPG` gas), `AgreementNumber`, `ClientNumber`, `PpNumber` (PPG
number), `Address` / `ClientAddress` / `InvoiceAddress` (`Ulica`, `UlicaTyp`, `NrBudynku`,
`NrLokalu`, `KodPocztowy`, `Miejscowosc`), `Active`, `StartDate`, `EndDate`, `ClientName`,
`Iban` (individual account to pay into), `EcoInvoice`, `Saldo`, `Region`, `Tariff`,
`AgreementName`, `Owner`, `CollectionPoints[]` (`NumberOSD`, `IdCRD`, `Address*`, `Billing`).

### Invoices

`/crm/get-invoices-v2`: `pageNumber`, `pageSize` (web app: 12; 200 for the payment dialog),
optional filters:

| Param | Meaning |
|---|---|
| `dateFrom`, `dateTo` | ISO timestamps, filter by issue date |
| `agreementNumber`, `clientNumber` | restrict to an agreement / customer |
| `paid=false` | unpaid only |
| `afterDeadline=true` | overdue |
| `loadAfter30Days=true` | forecast instalments due in more than 30 days |
| `excludeAfterDeadline=true` | not overdue ("upcoming" tab, combined with `paid=false`) |
| `beforeEndDate=true`, `forecastToPay=true`, `isHomeAssistant=true` | used by other screens |

`type=…` answers 400. Response: `InvoicesList[]`, `HasMoreRecords`, `AllowLoadAfter30Days`,
`AllowLoadAllInvoices`, `HasNonPaidForecast`. Item: `Number`, `Date`, `SellDate`,
`StartDate`/`EndDate` (billing period), `PayingDeadlineDate`, `GrossAmount`, `AmountToPay`,
`IsPaid`, `Status` (`Posted`), `Type`, `TempType` (`R` settlement, `P`/`B` forecast
instalments, empty for notes), `IsInterestNote`, `IsCreditNote`, `Correction`,
`AgreementNumber`, `IdPP`, `WearKWH`, `WearM3`, `Iban`, `PDFPrintAllowed`, `PdfExists`
(always false in practice; use the PDF endpoint).

| Endpoint | Params | Response |
|---|---|---|
| `/crm/get-invoice-details` | `invoiceNumber`, `excludePdfCheck=true` | `{Invoice: {...}}` + `Address`, `PdfVisibility`, `AutomaticPaymentDate`, `IsSubscribed` |
| `/crm/get-interest-note-details` | `interestNoteNumber`, `excludePdfCheck=true` | `{InterestNote: {DocumentNumber, DateCreated, DatePaymentDeadline, DateSell, GrossAmount, AmountToPay, IsPaid, …}}` |
| `/crm/get-invoice-pdf-visibility` | `invoiceNumber` | `{Visibility: "PdfVisible"}` |
| `/crm/get-invoice-pdf` | `invoiceNumber`, `mode=partial` | `application/pdf`, `Content-Disposition: inline; filename="p/…pdf"` |
| `/crm/get-interest-note-pdf` | `interestNoteNumber`, `mode=partial` | PDF, or `text/plain` "Brak podglądu PDF dla wybranej faktury." |

### Payments & history

| Endpoint | Params | Response |
|---|---|---|
| `/crm/get-client-payments` | – | `Payments[]`: `DocumentDate`, `DocumentNumber` (`KP/RAP/…`), `Value`, `PaymentType` (`P`), `Description`, `ClientNumber`, `Transfer` |
| `/crm/get-compensations` | – | `Compensations[]` (empty on the test account) |
| `/crm/get-refunds` | – | `Refunds[]` (empty on the test account) |
| `/crm/get-account-history` | `pageNumber`, `pageSize` | `HistoryList[]`: `Date`, `Type` ("Zapłata za fakturę", …), `Description` |

### Readings & consumption

| Endpoint | Params | Response |
|---|---|---|
| `/crm/get-all-ppg-readings-for-meter` | `idPpg`, `pageNumber`, `pageSize`, `ignoreStartDate=true` or `dateFrom`+`dateTo`, optional `type` | `MeterReadings[]`, `HasMoreRecords` |
| `/crm/get-ppg-readings-dates` | `idPpg` | `MeterReadingsDates[]` |
| `/crm/get-ppgs-readings-file` | `ppgIds` | xlsx attachment `Readings_YYYY_MM_DD_HH_MM_SS.xlsx` |
| `/crm/get-monthly-wear-chart-data` | `ppgIds`, `pageNumber`, `pageSize` | `ChartData: {"październik_2026": [{Label, Year, Value, Wear, Type, ReadingDateUtc, Period, ZoneLabel}]}` |
| `/crm/get-yearly-wear-chart-data` | `ppgIds` | `ComparisonPercent`, `IsPlusSignForPercent`, `ThisYearData[]` / `PreviousYearData[]`: `{Year, WearByYear, ChartItems[]}` |
| `/crm/get-wear-comparison-chart-data` | period params | not used |

Reading: `ReadingDateUtc`, `Value` (meter, m³), `Wear` (consumption since previous), `Value2/3`,
`Wear2/3` (multi-register meters), `Type` (`Real`, …), `Status` (`ROZL` settled,
`ANUL_KLIENT` cancelled by customer), `MeterNumber`, `PpId`, `ClientNumber`, `CanBeCancelled`.
The list only covers the current billing system's history (two readings on the test account).

### Messages & settings

| Endpoint | Params | Response |
|---|---|---|
| `/notification/get-notifications` | – | `Notifications[]`: `Id`, `Title`, `Body`, `DateCreatedUtc`, `Type` (`Invoices`, …), `ObjectId` (invoice number) |
| `/notification/get-unreaded-count` | – | `{UnreadedCount}` |
| `/notification/email-settings` | – | `{Settings: {System, Invoices}}` |
| `/contact/get-contact-history-v2` | `pageIndex`, `pageSize` | `Contacts[]`, `AllowLoadMore` (item shape not observed: empty on the test account) |
| `/contact/get-contact-message` | `PublicId` | `Answers`, `ContactMessage` (not used) |

## Write endpoints (not used by the SDK)

Mapped from the bundle only; never called while exploring:
`POST /crm/add-ppg-reading-v2` (submit a reading), `/crm/cancel-reading`,
`/crm/pay-for-invoice-v2` / `pay-for-multi-invoice-v2` (payments), `/notification/remove`,
`/agreements/set-agreement-name`, `/agreements/set-agreement-color`, `/cms/order-einvoice`,
`/crm/disable-eco-invoice`, `/contact/send-message-v2`, `/auth/change-password`,
`/auth/change-email-v2`, `/agreements/change-tariff`, `/agreements/send-terminate-agreement`.
