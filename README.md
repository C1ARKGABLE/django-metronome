# django-metronome

**Django integration for [Metronome](https://www.metronome.com/)** — usage metering, contracts, and invoicing — with a local mirror, sync commands, optional provisioning writes, and room to grow into webhooks and async processing.

> **Status:** Pre-1.0. Public APIs may still change; pin versions in production.

For **repository layout, commands, and agent-oriented conventions**, see [AGENTS.md](AGENTS.md).

## Why this exists

Metronome publishes an official Python SDK ([`metronome-sdk` on PyPI](https://pypi.org/project/metronome-sdk/)) and documents it under [Build with the Metronome SDKs](https://docs.metronome.com/developer-resources/sdks). That SDK is the right place for typed API calls, retries, and pagination.

**django-metronome** is not a replacement for the official client. It is a **Django layer** on top of it: ORM models, management commands, settings, and conventions so your app can treat Metronome as part of your data model — similar in spirit to how [dj-stripe](https://github.com/dj-stripe/dj-stripe) does for Stripe.

Metronome’s product surface (contracts, usage, invoices, credits, etc.) is documented in the [Metronome guides](https://docs.metronome.com/guides/get-started/home).

## What is implemented today

These align with the **foundation** (Phase 0), **read/sync MVP** (Phase 1), and **provisioning writes** (Phase 1.5) tracks in the project roadmap.

- **Settings and client** — `django_metronome.conf` exposes API key, webhook secret, environment, timeouts, retries, and feature flags. The app runs without credentials; API usage stays disabled until `METRONOME_API_KEY` is set.
- **Adapter boundary** — All Metronome HTTP goes through `MetronomeAdapter` (built on `client.py`). Callers outside the adapter should not import SDK types.
- **Pydantic schemas** — Shared validation under `django_metronome.schemas` (entities, webhooks, provisioning requests) to keep payloads stable as the API evolves.
- **Local mirror models** — `MetronomeCustomer`, `MetronomeContract`, `MetronomeRateCard`, `MetronomeRate`, `MetronomeInvoice`, `MetronomeUsageAggregate`, plus `SyncCheckpoint` for resumable sync.
- **Sync pipeline** — Idempotent upserts from list/retrieve APIs; management commands per entity and `sync_metronome_all` with checkpointing (`--reset-checkpoint` to start clean).
- **Provisioning** — Outbound customer, contract, and rate-card (+ rates) flows through the adapter, then **reconcile** the mirror via retrieve + the same upsert helpers as sync (no optimistic-only ORM writes).
- **Operator helpers** — List/diagnostic commands (`metronome_list_rate_cards`, `metronome_list_billable_metrics`, `metronome_validate_provisioning`) for sandbox exploration.

## Roadmap (not yet in this package)

- **Webhooks** — Verified ingestion, idempotent event storage, replay tooling.
- **Org / hierarchy** — Contract hierarchy, payer semantics, grouped usage dimensions.
- **Task durability** — Pluggable background processing after an evaluation of backends (e.g. Redis vs RabbitMQ).
- **Local vs live reads** — Query facade toggling mirrored DB vs direct SDK reads, with drift diagnostics.
- **Integrations** — Optional dj-stripe linking, dynamic rate-card workflows, and similar extensions behind flags.

## Non-goals

- **Payment collection** (cards, bank debits, SCA) — typically handled by a payments provider; Metronome focuses on metering, pricing, contracts, and invoicing. This package documents that boundary.
- **Re-implementing the Metronome HTTP API** — use the official SDK inside the adapter.

## Requirements

- **Python** 3.12 or 3.13 (see `pyproject.toml`; 3.14+ when Django supports it)
- **Django** 5.2.x (pinned range in Poetry)
- **`metronome-sdk`** — used by the integration adapter for API calls

## Installation

Not published yet. When ready:

```bash
pip install django-metronome
```

Until then, use a git checkout with [Poetry](https://python-poetry.org/docs/#installation) (see Development below).

## Development

The reusable app and the smoke **example** project were created with Django’s built-in commands ([`django-admin` / `manage.py`](https://docs.djangoproject.com/en/stable/ref/django-admin/)), following the spirit of [How to write reusable apps](https://docs.djangoproject.com/en/stable/intro/reusable-apps/).

From the repository root:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install poetry
poetry install
```

Scaffolding commands (already reflected in the tree; re-run only if you recreate from scratch):

```bash
mkdir -p src/django_metronome
poetry run django-admin startapp django_metronome src/django_metronome
mkdir -p example
poetry run django-admin startproject example_site example
```

Apply migrations and run the example site (serves **Hello, world** at `/`):

```bash
poetry run python example/manage.py migrate
poetry run python example/manage.py runserver
```

Run tests and lint (or use `make test`, `make lint`, `make fmt`, `make check`):

```bash
poetry run pytest
poetry run ruff check src tests example
poetry run ruff format src tests example
```

The **installable package** is `src/django_metronome/`. The **`example/`** directory is dev-only and is not the published library surface.

## Metronome configuration

Integration settings are defined in `django_metronome.conf` (`get_metronome_settings()`). The app boots without credentials by default; SDK calls only activate when an API key is configured.

Supported settings (Django settings values or environment variables):

- `METRONOME_API_KEY` (optional, enables API calls when present)
- `METRONOME_WEBHOOK_SECRET` (optional, reserved for future webhook signature verification)
- `METRONOME_ENV` (`sandbox`, `production`, or `local`; default `sandbox`)
- `METRONOME_TIMEOUT_MS` (default `10000`)
- `METRONOME_MAX_RETRIES` (default `2`)
- `METRONOME_STRICT_SCHEMA_MODE` (default `false`)
- `METRONOME_USE_LIVE_QUERIES` (default `false`; forward-looking flag for a local-vs-live query layer)

Example `example/example_site/settings.py` override:

```python
METRONOME_API_KEY = os.getenv("METRONOME_API_KEY")
METRONOME_WEBHOOK_SECRET = os.getenv("METRONOME_WEBHOOK_SECRET")
METRONOME_ENV = os.getenv("METRONOME_ENV", "sandbox")
METRONOME_TIMEOUT_MS = int(os.getenv("METRONOME_TIMEOUT_MS", "10000"))
METRONOME_MAX_RETRIES = int(os.getenv("METRONOME_MAX_RETRIES", "2"))
METRONOME_STRICT_SCHEMA_MODE = os.getenv("METRONOME_STRICT_SCHEMA_MODE", "false").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
METRONOME_USE_LIVE_QUERIES = os.getenv("METRONOME_USE_LIVE_QUERIES", "false").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
```

## Sync (Phase 1)

Backfill and incremental sync populate the local mirror from Metronome list/retrieve APIs. Commands share **`--environment`** (mirror row label), **`--limit`** (page size), and **`--reset-checkpoint`** (discard saved cursor for that entity).

Requires `METRONOME_API_KEY`.

```bash
poetry run python example/manage.py sync_metronome_customers
poetry run python example/manage.py sync_metronome_contracts
poetry run python example/manage.py sync_metronome_rate_cards
poetry run python example/manage.py sync_metronome_invoices
poetry run python example/manage.py sync_metronome_usage
poetry run python example/manage.py sync_metronome_all
```

## Provisioning (Phase 1.5)

Outbound **writes** (customers, contracts, rate cards + rates) go only through `django_metronome.services.MetronomeAdapter`. After each successful Metronome API call, the package reconciles the **local mirror** using retrieve / targeted reads and the same `upsert_*` helpers used by sync — never optimistic writes alone.

**Python API**

- `provision_customer`, `update_customer_ingest_aliases`, `provision_contract`, `provision_rate_card_with_rates` live in `django_metronome.services.provisioning`.
- Request shapes: `CustomerCreateRequest`, `ContractCreateRequest`, `RateCardCreateRequest`, `RateAddRequest` in `django_metronome.schemas.provisioning`.
- Errors from the SDK are wrapped as `MetronomeProvisioningError` via `translate_sdk_exception` (see `django_metronome.services.errors`). Conflicts such as duplicate `uniqueness_key` surface without applying mirror changes.

**Management commands** (require `METRONOME_API_KEY`; same `--environment` label as sync):

```bash
poetry run python example/manage.py metronome_provision_customer --name "Acme Corp" --ingest-alias my-org-slug
poetry run python example/manage.py metronome_provision_contract \
  --customer-id "<metronome_customer_uuid>" \
  --starting-at "2026-01-01T00:00:00Z" \
  --kwargs-json '{"rate_card_alias":"paygo","name":"Self-serve"}'
poetry run python example/manage.py metronome_provision_rate_card \
  --name "Standard" \
  --alias standard-pricing \
  --rates-json '[{"product_id":"<uuid>","rate_type":"FLAT","starting_at":"2026-01-01T00:00:00Z","price":0.01,"entitled":true}]'
```

Use `--kwargs-json` / `--rates-json` for SDK fields not exposed as flags. Contract create uses **v1**; mirror reconciliation uses **v2** `contracts.retrieve`.

### Git hooks (format + lint before commit/push)

After `poetry install`, register hooks once per clone:

```bash
make install-hooks
```

That installs [pre-commit](https://pre-commit.com/) for **commit** and **push** (Ruff format, Ruff check with auto-fix, trailing whitespace, EOF, YAML, large files). To run the same checks manually:

```bash
make pre-commit
```

CI runs the same `pre-commit` suite plus `pytest` (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## Documentation

- Metronome product & API: [docs.metronome.com](https://docs.metronome.com/guides/get-started/home)
- Official Python SDK: [metronome-sdk](https://pypi.org/project/metronome-sdk/) · [metronome-python](https://github.com/Metronome-Industries/metronome-python)

## License

MIT — see [LICENSE](LICENSE).
