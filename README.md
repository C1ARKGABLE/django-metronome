# django-metronome

**Django integration for [Metronome](https://www.metronome.com/)** — usage metering, contracts, and invoicing — with first-class support for webhooks, persisted models, and safe sync patterns in Django apps.

> **Status:** Early design / pre-1.0. APIs and scope will change.

For **repository layout, commands, and agent-oriented conventions**, see [AGENTS.md](AGENTS.md).

## Why this exists

Metronome publishes an official Python SDK ([`metronome-sdk` on PyPI](https://pypi.org/project/metronome-sdk/)) and documents it under [Build with the Metronome SDKs](https://docs.metronome.com/developer-resources/sdks). That SDK is the right place for typed API calls, retries, and pagination.

**django-metronome** is not a replacement for the official client. It is a **Django layer** on top of it: ORM models, webhook endpoints, settings, management commands, and conventions so your app can treat Metronome as part of your data model — similar in spirit to how [dj-stripe](https://github.com/dj-stripe/dj-stripe) does for Stripe.

Metronome’s product surface (contracts, usage, invoices, credits, etc.) is documented in the [Metronome guides](https://docs.metronome.com/guides/get-started/home).

## Planned features

- **Webhook ingestion** — Verify and process Metronome webhooks; map events to upserts on local models (idempotent, replay-safe patterns).
- **ORM models** — Mirror the Metronome objects your app needs (exact set TBD against the [Metronome API](https://docs.metronome.com/api)): e.g. customer linkage, contracts, billable metrics, usage aggregates, credits, invoice state — aligned to your product’s read/write paths.
- **API sync / backfill** — Repair and bootstrap when webhooks were missed or for migrations; wrap the official SDK with Django-friendly batching and logging.
- **Settings & multi-environment** — Sensible defaults for API keys / base URLs; support for sandbox vs production (and multiple logical environments if you need them).
- **Usage emission helpers** — Thin helpers for common “record usage from Django” flows, delegating transport to `metronome-sdk`.
- **Tests & versioning** — Pin and document tested Metronome API / SDK versions; fixture-driven tests.

## Non-goals

- **Payment collection** (cards, bank debits, SCA) — typically handled by a payments provider; Metronome focuses on metering, pricing, contracts, and invoicing. This package will document that boundary clearly.
- **Re-implementing the Metronome HTTP API** — use the official SDK for all API traffic.

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

Phase 0 introduces an explicit settings contract in `django_metronome.conf`.
The app boots without credentials by default; SDK calls only activate when an
API key is configured.

Supported settings (Django settings values or environment variables):

- `METRONOME_API_KEY` (optional, enables API calls when present)
- `METRONOME_WEBHOOK_SECRET` (optional, for webhook signature verification)
- `METRONOME_ENV` (`sandbox`, `production`, or `local`; default `sandbox`)
- `METRONOME_TIMEOUT_MS` (default `10000`)
- `METRONOME_MAX_RETRIES` (default `2`)
- `METRONOME_STRICT_SCHEMA_MODE` (default `false`)
- `METRONOME_USE_LIVE_QUERIES` (default `false`)

Example `example/example_site/settings.py` override:

```python
METRONOME_API_KEY = os.getenv("METRONOME_API_KEY")
METRONOME_WEBHOOK_SECRET = os.getenv("METRONOME_WEBHOOK_SECRET")
METRONOME_ENV = os.getenv("METRONOME_ENV", "sandbox")
METRONOME_TIMEOUT_MS = int(os.getenv("METRONOME_TIMEOUT_MS", "10000"))
METRONOME_MAX_RETRIES = int(os.getenv("METRONOME_MAX_RETRIES", "2"))
METRONOME_STRICT_SCHEMA_MODE = os.getenv("METRONOME_STRICT_SCHEMA_MODE", "false")
METRONOME_USE_LIVE_QUERIES = os.getenv("METRONOME_USE_LIVE_QUERIES", "false")
```

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
