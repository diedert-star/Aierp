# Architecture — Invoice Intake Core (Stage 1)

Document intake layer for an AI-native Benelux SME accounting system: ingest → canonical
record → validation → counterparty resolution. No GL posting, no LLM calls in this stage.

## Principles

- **Original file is the legal record.** Immutable, content-addressed, reproducible from
  blob storage alone (bewaarplicht 7/10 years).
- **One canonical schema, format-blind.** Every extractor (UBL now, PDF stub, image later)
  produces the same `CanonicalInvoice` shape. Downstream code never branches on source format.
- **Append-only history.** Canonical extractions and validation runs are versioned rows,
  never mutated in place. A re-extraction or re-validation creates a new row.
- **Deterministic validation.** No model, no heuristics — stable codes, typed params,
  Dutch messages, both severities always fully evaluated (no short-circuit).
- **Strict layering.** Each stage is an independently importable/testable package.
  Dependency direction is one-way: `stage1 ← stage2 ← stage3 ← stage4 ← pipeline ← api`.
  No stage imports from a later-numbered stage. `pipeline` is the composition root, not
  a stage itself, so it may import all of them.

## Repo layout

```
aierp/
├── pyproject.toml
├── alembic.ini
├── ARCHITECTURE.md
├── src/aierp/
│   ├── config.py               # Settings (Pydantic BaseSettings): DB DSN, blob root, VIES config
│   ├── db.py                   # SQLAlchemy engine/session factory, declarative Base
│   │
│   ├── enums.py                # Shared enums (see Data model). Imported by every stage.
│   │
│   ├── blob_store/              # No dependency on any stage.
│   │   ├── protocol.py         # BlobStore Protocol: put/get/exists/delete(never)
│   │   └── local.py            # LocalFilesystemBlobStore
│   │
│   ├── stage1_ingest/
│   │   ├── models.py           # SourceDocument ORM model
│   │   ├── schemas.py          # IngestRequest/IngestResult Pydantic models
│   │   ├── service.py          # ingest_document(): hash, store, insert-or-return-duplicate
│   │   └── router.py           # POST /documents
│   │
│   ├── stage2_extraction/
│   │   ├── models.py           # CanonicalInvoiceRecord ORM model (JSONB + version)
│   │   ├── schemas.py          # CanonicalInvoice, Party, InvoiceLine, VatBreakdown, Totals
│   │   ├── protocol.py         # Extractor Protocol
│   │   ├── ubl_extractor.py    # UblExtractor
│   │   ├── pdf_extractor.py    # PdfExtractor (stub, raises NotImplementedError)
│   │   └── repository.py       # persist_canonical_invoice() — always inserts new version
│   │
│   ├── stage3_validation/
│   │   ├── codes.py             # ValidationCode enum, ValidationResult schema
│   │   ├── iban.py              # mod-97 checksum
│   │   ├── vat_number.py        # per-country structural regex validation
│   │   ├── vies_client.py       # cached, rate-limited, failure-tolerant VIES lookup
│   │   ├── checks.py            # one function per check, pure, returns list[ValidationResult]
│   │   └── service.py           # run_all_checks() — runs every check, never short-circuits
│   │
│   ├── stage4_counterparty/
│   │   ├── models.py            # Counterparty, CounterpartyAlias ORM models
│   │   ├── schemas.py           # CounterpartyMatch
│   │   ├── normalize.py         # name normalization (case, legal forms, punctuation)
│   │   └── service.py           # resolve_counterparty()
│   │
│   ├── pipeline/                 # Composition root — may import stages 1-4.
│   │   ├── reasons.py            # ReviewReason enum + typed param models
│   │   ├── models.py             # DocumentPipelineState ORM model (the read model)
│   │   ├── orchestrator.py       # run_pipeline(document_id): extract → validate → resolve → classify
│   │   └── repository.py        # upsert pipeline state
│   │
│   ├── api/
│   │   ├── app.py                # FastAPI app factory, router registration
│   │   ├── deps.py               # tenant_id header dependency (stub, no auth)
│   │   └── documents_router.py   # GET /documents?status=needs_review
│   │
│   └── alembic/
│       ├── env.py
│       └── versions/
│
└── tests/
    ├── conftest.py               # DB fixture (transactional, rollback per test), tmp blob store
    ├── fixtures/ubl/*.xml        # see Test fixtures
    ├── stage1_ingest/test_service.py
    ├── stage2_extraction/test_ubl_extractor.py
    ├── stage2_extraction/test_pdf_extractor.py
    ├── stage3_validation/test_arithmetic.py
    ├── stage3_validation/test_identity.py
    ├── stage3_validation/test_semantics.py
    ├── stage3_validation/test_duplicates.py
    ├── stage4_counterparty/test_resolution.py
    └── pipeline/test_end_to_end.py
```

## Data model

All tables live in Postgres, one migration per stage. `tenant_id` is a plain indexed
string column throughout (no `tenant` table — out of scope per "auth beyond a header stub").

### `source_document` (stage 1)

| column             | type                          | notes                                   |
|--------------------|-------------------------------|------------------------------------------|
| id                 | UUID PK                       |                                          |
| tenant_id          | text, indexed                 |                                          |
| sha256             | char(64)                      | unique together with tenant_id           |
| blob_key           | text                           | content-addressed, see below            |
| channel            | enum `Channel`                | peppol / email / upload / mobile        |
| original_filename  | text, nullable                |                                          |
| mime_type          | text                           |                                          |
| byte_size          | bigint                        |                                          |
| received_at        | timestamptz                   |                                          |
| ingest_status      | enum `IngestStatus`           | `received` (stage 1 only ever writes this; later stages track their own status elsewhere, never mutate this column) |

Unique constraint: `(tenant_id, sha256)`. Blob key derivation:
`f"{tenant_id}/{sha256[:2]}/{sha256[2:4]}/{sha256}"` — no extension needed, content is
addressed by hash; `mime_type` on the row tells you how to interpret it.

### `canonical_invoice` (stage 2)

| column               | type          | notes                                          |
|----------------------|---------------|-------------------------------------------------|
| id                   | UUID PK       |                                                  |
| document_id          | FK → source_document.id |                                        |
| version              | int           | 1, 2, 3… per document, never reused             |
| extractor_name       | text          | denormalized from `data` for querying           |
| extractor_version    | text          |                                                  |
| data                 | JSONB         | full `CanonicalInvoice` (see schema below), Decimal fields serialized as strings |
| created_at           | timestamptz   |                                                  |

Unique constraint: `(document_id, version)`. Never updated — a re-extraction inserts
`version = max(version) + 1`. "Current" = highest version per document.

### `canonical_invoice`.data → `CanonicalInvoice` (Pydantic v2, the schema in the prompt)

```python
class Party(BaseModel):
    name: str
    vat_number: str | None
    kbo_or_kvk_number: str | None
    iban: str | None
    address: str | None
    country_code: str | None   # ISO 3166-1 alpha-2

class InvoiceLine(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    net_amount: Decimal
    vat_rate: Decimal          # e.g. 0.21
    vat_amount: Decimal

class VatBreakdownEntry(BaseModel):
    rate: Decimal
    taxable_base: Decimal
    vat_amount: Decimal
    exemption_reason_code: str | None

class Totals(BaseModel):
    net: Decimal
    vat: Decimal
    gross: Decimal
    prepaid: Decimal
    payable: Decimal

class ExtractorInfo(BaseModel):
    name: str
    version: str

class CanonicalInvoice(BaseModel):
    document_id: UUID
    supplier: Party
    buyer: Party
    invoice_number: str
    invoice_date: date
    due_date: date | None
    currency: str                          # ISO 4217, e.g. "EUR"
    lines: list[InvoiceLine]
    vat_breakdown: list[VatBreakdownEntry]
    totals: Totals
    payment_reference: str | None
    extraction_confidence: dict[str, float]  # field path -> 0..1
    extractor: ExtractorInfo
```

All monetary/quantity fields are `Decimal`, never `float` — arithmetic checks in stage 3
depend on exact decimal comparison with an explicit tolerance.

### `validation_run` + `validation_result` (stage 3)

Validation is re-run whenever the canonical record changes or on demand; each run is a
new group of rows so history is auditable.

| `validation_run`     | type        |
|-----------------------|------------|
| id (UUID PK)          |            |
| document_id (FK)      |            |
| canonical_invoice_id (FK) | which version was validated |
| created_at            |            |

| `validation_result`  | type                          |
|-----------------------|------------------------------|
| id (UUID PK)          |                               |
| run_id (FK)           |                               |
| code                  | enum `ValidationCode`         |
| severity              | enum `error` \| `warning`     |
| message_nl            | text                          |
| params                | JSONB                         |

`ValidationResult` (the Pydantic return type of each check function) mirrors this row
1:1 and is what stage-3 unit tests assert against directly, independent of the DB.

### `counterparty` + `counterparty_alias` (stage 4)

| `counterparty`        | type                                    |
|------------------------|-----------------------------------------|
| id (UUID PK)           |                                          |
| tenant_id (indexed)    |                                          |
| display_name           | text                                    |
| status                 | enum `unconfirmed` \| `confirmed`       |
| created_at / updated_at |                                         |

| `counterparty_alias`  | type                                                |
|------------------------|------------------------------------------------------|
| id (UUID PK)           |                                                        |
| counterparty_id (FK)   |                                                        |
| tenant_id (indexed)    | denormalized, avoids a join for lookup                |
| alias_type             | enum `name` \| `vat_number` \| `iban`                  |
| raw_value              | text                                                   |
| normalized_value       | text, indexed                                          |
| first_seen_at          | timestamptz                                            |

Unique constraint: `(tenant_id, alias_type, normalized_value)`. Exact-match resolution
(stage 4, steps 1-2) is a lookup against this table by `alias_type='vat_number'` or
`'iban'`. Fuzzy match (step 3) compares `normalized_value` for `alias_type='name'` using
trigram similarity (`pg_trgm`) above a configurable threshold. Every name variant and
every IBAN ever seen on an incoming invoice is inserted here (even for confirmed
matches), so future resolution improves with volume.

### `document_pipeline_state` (pipeline — the read model behind `GET /documents`)

| column                       | type                              |
|-------------------------------|-----------------------------------|
| document_id (PK, FK)          |                                    |
| status                        | enum `DocumentStatus`: `clean` \| `needs_review` |
| reasons                       | JSONB — ordered `list[{code, params}]`, see below |
| canonical_invoice_id (FK, null)|                                   |
| counterparty_id (FK, null)    |                                    |
| counterparty_match_strategy   | enum, null                        |
| counterparty_match_confidence | float, null                       |
| updated_at                    |                                    |

This is the only table the API reads for `GET /documents`; it is written once per
pipeline run (upsert on `document_id`) by the orchestrator, after stages 2-4 complete.

## Stage contracts

### `BlobStore` protocol

```python
class BlobStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...   # no-op if key exists (immutable)
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
```

`LocalFilesystemBlobStore(root: Path)` implements it now; an S3-compatible one comes
later behind the same protocol. Nothing outside `blob_store/` touches the filesystem.

### `Extractor` protocol

```python
class Extractor(Protocol):
    name: str
    version: str
    def extract(self, raw_bytes: bytes, *, document_id: UUID) -> CanonicalInvoice: ...
```

- `UblExtractor` — parses UBL 2.1 / Peppol BIS Billing 3.0 via `lxml`. Maps EN 16931
  core fields directly (`cbc:ID`, `cbc:IssueDate`, `cac:AccountingSupplierParty`, line
  items, `cac:TaxTotal/cac:TaxSubtotal`, payment means, `PaymentID` for the structured
  reference). Confidence is `1.0` for every field present in the source XML, absent for
  fields the document doesn't carry. Unrecognized extensions are logged and skipped —
  never raise on them.
- `PdfExtractor` — `extract()` raises `NotImplementedError("PDF extraction not yet implemented; stage 1 covers UBL only")`.
  Tests assert the protocol shape (has `.name`/`.version`, raises with that message) so
  the contract is pinned before a real implementation lands.

### Validation checks (stage 3)

Each check is a pure function `(CanonicalInvoice, ValidationContext) -> list[ValidationResult]`,
where `ValidationContext` carries tenant VAT number, a VIES client, and a lookup for
existing (supplier_vat, invoice_number) / (supplier, gross_amount, date) pairs already
booked for this tenant — stage 3 itself stays DB-agnostic; the context is assembled by
the orchestrator. `run_all_checks()` calls every check unconditionally and concatenates
results — no short-circuiting.

`ValidationCode` (stable, stage-3-owned):

| code                         | severity | params                                   |
|-------------------------------|----------|-------------------------------------------|
| `VAT_RATE_ARITHMETIC_MISMATCH` | error    | rate, taxable_base, expected_vat, actual_vat |
| `VAT_BREAKDOWN_TOTAL_MISMATCH` | error    | expected, actual                          |
| `LINE_NET_TOTAL_MISMATCH`      | error    | expected, actual                          |
| `TOTALS_GROSS_MISMATCH`        | error    | net, vat, gross                           |
| `SUPPLIER_VAT_STRUCTURALLY_INVALID` | error | vat_number, country_code             |
| `SUPPLIER_VAT_VIES_INVALID`    | error    | vat_number                                |
| `VIES_UNAVAILABLE`             | warning  | vat_number                                |
| `SUPPLIER_IBAN_CHECKSUM_INVALID` | error  | iban                                      |
| `INVOICE_DATE_IN_FUTURE`       | error    | invoice_date                              |
| `INVOICE_DATE_TOO_OLD`         | warning  | invoice_date, months_old                  |
| `BUYER_VAT_MISMATCH`           | error    | expected, actual                          |
| `CURRENCY_NOT_EUR`             | warning  | currency                                  |
| `DUPLICATE_INVOICE`            | error    | existing_document_id                      |
| `NEAR_DUPLICATE_INVOICE`       | warning  | existing_document_id, days_apart          |

### Counterparty resolution (stage 4)

```python
class CounterpartyMatch(BaseModel):
    counterparty_id: UUID
    strategy: MatchStrategy         # vat_exact | iban_exact | fuzzy_name | new
    confidence: float
    is_provisional: bool            # True for fuzzy_name and new
```

`resolve_counterparty(session, tenant_id, supplier: Party) -> CounterpartyMatch`
tries VAT-exact, then IBAN-exact, then normalized fuzzy name (strip BV/NV/BVBA/VOF/
GmbH/… legal-form suffixes, lowercase, strip punctuation, trigram similarity ≥
threshold). A fuzzy hit never auto-confirms — it returns the match with
`is_provisional=True` so the pipeline routes to review. No match at all creates a new
`counterparty` row with `status='unconfirmed'` plus its first aliases, and also returns
`is_provisional=True`.

### Pipeline orchestrator & review reasons

`run_pipeline(session, document_id)`:
1. Load `source_document`.
2. Extract (stage 2) → on `NotImplementedError`, record reason `EXTRACTION_NOT_SUPPORTED`
   and stop (no canonical record to validate against).
3. Persist canonical record, run all validation checks (stage 3).
4. Resolve counterparty (stage 4).
5. Classify: `status = clean` iff there are zero validation results (error *or*
   warning) **and** the counterparty match is an exact, non-provisional match.
   Otherwise `needs_review`, with `reasons` = validation results converted 1:1 into
   `ReviewReason` entries, plus (if provisional) `COUNTERPARTY_UNCONFIRMED` /
   `FIRST_INVOICE_FROM_SUPPLIER` appended last.
6. Upsert `document_pipeline_state`.

`ReviewReason` (pipeline-owned enum, typed params, Dutch `message()` per variant) wraps
every `ValidationCode` plus two pipeline-level reasons:

- `FIRST_INVOICE_FROM_SUPPLIER` — new counterparty created (no params)
- `COUNTERPARTY_UNCONFIRMED` — fuzzy match only (params: candidate_name, confidence)
- `EXTRACTION_NOT_SUPPORTED` — channel/mime not yet handled (params: channel, mime_type)

Example rendering: `VAT_RATE_ARITHMETIC_MISMATCH` →
*"BTW-bedrag wijkt 4,20 EUR af van het berekende bedrag (21% van 320,00 EUR = 67,20 EUR, factuur vermeldt 71,40 EUR)"*.

## API

- `POST /documents` — multipart file + `channel` + `tenant_id` (header stub, see
  `api/deps.py`). Returns `{document_id, duplicate: bool}`. Synchronously runs the full
  pipeline after ingest (stage sizes here don't warrant a queue yet).
- `GET /documents?status=needs_review` — returns each document's `document_id`,
  `status`, `reasons` (code + rendered Dutch message + params), the current canonical
  record, and a blob link (`/documents/{id}/original`, streamed from `BlobStore`).

## Test fixtures (`tests/fixtures/ubl/`)

Built before any implementation code:

1. `valid_be_domestic_21.xml` — single 21% line, clean.
2. `valid_mixed_21_6.xml` — two VAT rates, clean.
3. `valid_intracommunity_reverse_charge.xml` — 0% + `exemption_reason_code`, clean.
4. `invalid_vat_arithmetic.xml` — `VAT_RATE_ARITHMETIC_MISMATCH`.
5. `duplicate_of_valid_be_domestic_21.xml` — byte-identical copy of fixture 1 (tests
   stage 1 dedup on sha256 *and*, separately, stage 3 `DUPLICATE_INVOICE` once booked).
6. `near_duplicate_of_valid_be_domestic_21.xml` — same supplier/gross, +2 days, different
   invoice number → `NEAR_DUPLICATE_INVOICE`.
7. `unknown_supplier.xml` — supplier with no existing `counterparty` row →
   `FIRST_INVOICE_FROM_SUPPLIER`.
8. `malformed_supplier_vat.xml` — VAT number that fails the country-prefix structural
   regex → `SUPPLIER_VAT_STRUCTURALLY_INVALID`.

Every check in stage 3 gets a passing and a failing unit test independent of these
fixtures too (constructing `CanonicalInvoice` objects directly is faster than round-
tripping XML for the arithmetic/IBAN/VAT-regex cases). VIES is mocked everywhere in
tests — no test hits the network.

## Assumptions to confirm before implementation

1. **Synchronous pipeline.** `POST /documents` runs stage 2-4 inline before responding.
   Given real-world volumes this is fine for stage 1; a queue can replace this later
   without changing any stage's contract.
2. **Duplicate detection scope.** "Same supplier VAT + invoice_number already booked"
   is read from `document_pipeline_state`/`canonical_invoice` for the tenant — I'm
   treating "booked" as "has a canonical record", not "posted to a ledger" (no ledger
   exists yet).
3. **Fuzzy name matching** uses Postgres `pg_trgm` similarity rather than pulling in a
   separate fuzzy-matching library — avoids an extra dependency, keeps it in SQL, and
   is trivially mockable in unit tests via the normalization function alone.
4. **VIES client** — stubbed as an interface with an in-memory TTL cache in stage 3;
   the real SOAP call and its rate limiting are implemented in stage 3 too (it's a
   validation concern), but every test mocks it.

Stopping here for review, as requested, before writing any code.
