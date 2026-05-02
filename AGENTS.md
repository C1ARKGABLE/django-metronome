# AGENTS.md — django-metronome

Instructions for humans and coding agents working in this repository.

## What this is

**django-metronome** is a **reusable Django app** (installable Python package) for integrating [Metronome](https://www.metronome.com/) billing. It layers on top of the official [`metronome-sdk`](https://pypi.org/project/metronome-sdk/); it does not replace it.

**Design stance (from the implementation roadmap):**

- **Read/sync first:** Phase 1 is a dj-stripe-style **local mirror** populated by list/retrieve APIs — not CRUD-first from Django.
- **Writes are isolated:** Phase 1.5 provisioning goes **only** through `MetronomeAdapter`; after each successful write, **reconcile** the mirror with retrieve + existing `upsert_*` (or a narrow sync), not duplicate business rules in Django.
- **SDK volatility:** Keep direct SDK usage in `client.py` + `services/metronome_adapter.py`. Map responses through Pydantic where practical; preserve unknown fields in `raw_payload` on mirror models.

## Repository map

| Path | Role |
|------|------|
| [`src/django_metronome/`](src/django_metronome/) | **Published library** — models, services, schemas, management commands, URLs/views. |
| [`src/django_metronome/conf.py`](src/django_metronome/conf.py) | **Settings dataclass** — `get_metronome_settings()`; env + Django settings overrides. |
| [`src/django_metronome/client.py`](src/django_metronome/client.py) | **SDK construction only** — configured `metronome-sdk` client. |
| [`src/django_metronome/services/metronome_adapter.py`](src/django_metronome/services/metronome_adapter.py) | **Only layer that calls the SDK** — reads, writes, pagination/version details stay here. |
| [`src/django_metronome/services/sync.py`](src/django_metronome/services/sync.py) | **Mirror ingestion** — `sync_*`, `upsert_*`, checkpoint-aware pagination. |
| [`src/django_metronome/services/provisioning.py`](src/django_metronome/services/provisioning.py) | **Outbound provisioning** — validate → adapter write → retrieve → upsert reconcile. |
| [`src/django_metronome/schemas/`](src/django_metronome/schemas/) | **Pydantic contracts** — entities, webhooks, provisioning requests (`schemas/provisioning.py`). |
| [`src/django_metronome/models.py`](src/django_metronome/models.py) | **ORM mirror** — `MetronomeCustomer`, `MetronomeContract`, `MetronomeRateCard`, `MetronomeRate`, `MetronomeInvoice`, `MetronomeUsageAggregate`, `SyncCheckpoint`; shared bases (`MetronomeSyncBaseModel`). |
| [`example/`](example/) | **Dev-only** Django project. Not the product API surface. Prefer management commands over editing `manage.py` / ASGI/WSGI glue. |
| [`tests/`](tests/) | **pytest-django**; `DJANGO_SETTINGS_MODULE` and `pythonpath` in [`pyproject.toml`](pyproject.toml). |
| [`pyproject.toml`](pyproject.toml) | **Poetry**, **Ruff**, **pytest**. |
| [`.pre-commit-config.yaml`](.pre-commit-config.yaml) | **Git hooks** — Ruff format + check (with `--fix`), whitespace/YAML guards; commit + push. |
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | **CI** — same as `make pre-commit` + `pytest` on push/PR. |
| [`README.md`](README.md) | User-facing overview, sync/provisioning commands, configuration. |

External references when implementing Metronome behavior:

- [Metronome docs](https://docs.metronome.com/guides/get-started/home)
- [Metronome API](https://docs.metronome.com/api)
- [Django reusable apps](https://docs.djangoproject.com/en/stable/intro/reusable-apps/)
- [Django logging](https://docs.djangoproject.com/en/stable/topics/logging/)

## Phases (what exists vs next)

Use this to scope patches and avoid mixing concerns.

| Phase | Focus | Status in codebase |
|-------|--------|-------------------|
| **0** | Dependencies, `conf`, client, adapter boundary, base models, Pydantic schemas | **Implemented** — see `conf.py`, `client.py`, `services/metronome_adapter.py`, `schemas/`, `models.py` bases. |
| **1** | Mirror models, mappers/sync, checkpointed commands, admin/query helpers | **Implemented** — `services/sync.py`, `sync_metronome_*` commands, `SyncCheckpoint`, queryset helpers (e.g. `MetronomeContract.objects.current_for_customer`). |
| **1.5** | Adapter write methods, provisioning service, reconcile-after-write, operator commands | **Implemented** — `services/provisioning.py`, `schemas/provisioning.py`, `metronome_provision_*`, `MetronomeProvisioningError`. |
| **2** | Webhooks: signature verify, idempotent event log, replay | **Not implemented** — do not duplicate webhook pipeline under provisioning. |
| **3** | Org/hierarchy, permissioned usage dimensions | **Not implemented**. |
| **4** | Durable task backend (evaluate Redis vs RabbitMQ); pluggable processor | **Not implemented** — provisioning may stay synchronous until then. |
| **5** | Local vs live query facade, drift diagnostics | **Partially prepared** — `METRONOME_USE_LIVE_QUERIES` flag in `conf`; facade not shipped. |
| **6** | dj-stripe linking, dynamic rate-card automation, opt-in advanced modules | **Not implemented**. |

## Management commands (library)

**Sync** (inherit shared args from `_sync_base.SyncCommandMixin`: `--environment`, `--limit`, `--reset-checkpoint`):

- `sync_metronome_customers`, `sync_metronome_contracts`, `sync_metronome_rate_cards`, `sync_metronome_invoices`, `sync_metronome_usage`, `sync_metronome_all`

**Provisioning:**

- `metronome_provision_customer`, `metronome_provision_contract`, `metronome_provision_rate_card`

**Diagnostics / lists:**

- `metronome_list_rate_cards`, `metronome_list_billable_metrics`, `metronome_validate_provisioning`

## Environment

- **Python:** 3.12 or 3.13 only (`requires-python` in `pyproject.toml`; extend when Django supports newer versions).
- From repo root, use a virtualenv and Poetry:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install poetry
poetry install
```

## Commands to use (copy-paste)

Run from the **repository root** with the venv activated (or use `poetry run` as below):

```bash
poetry run pytest
poetry run ruff check src tests example
poetry run ruff format src tests example
poetry run python example/manage.py migrate
poetry run python example/manage.py runserver
```

Shorter aliases (same commands):

```bash
make test
make lint
make fmt
make pre-commit   # same hooks as CI (see note below)
```

### Git hooks (once per clone)

```bash
make install-hooks
```

That registers **pre-commit** and **pre-push** hooks so Ruff format/check and basic hygiene run before commits and pushes (matches [`.pre-commit-config.yaml`](.pre-commit-config.yaml)).

**Note:** `pre-commit run --all-files` (and CI) only inspect **git-tracked** files. After adding new files, run `git add` before `make pre-commit`, or the first commit will still pick them up via the hook’s file list.

After substantive edits, run **`make check`** and/or **`make pre-commit`** before considering work done.

## Conventions

- **Library vs example:** All reusable code belongs in `src/django_metronome/`. The `example/` tree is for local smoke runs and integration checks only.
- **Django style:** Use `path()` / `re_path()` from `django.urls`, not legacy `url()`. Reusable apps: subclass `AppConfig`, set `name`, `label`, and `default_auto_field` explicitly (see [`src/django_metronome/apps.py`](src/django_metronome/apps.py)).
- **Formatting and lint:** **Ruff** is authoritative — run `make fmt` or rely on **`make install-hooks`** so commits/pushes auto-format and fix via pre-commit. Generated `example/**` code may ignore `E501` per `pyproject.toml`; still avoid unnecessary churn there.
- **Metronome HTTP:** Use **`metronome-sdk` only inside `client.py` / `MetronomeAdapter`** — no ad hoc raw HTTP clients for Metronome in this repo.
- **New features:** Match the phase boundaries above (e.g. webhook storage belongs in Phase 2, not in provisioning).
- **Payments:** Card capture / SCA / PSP flows are **out of scope**; document boundaries in PRs if touching billing UX.

## Tests

- Add new tests under [`tests/`](tests/) as `test_*.py`.
- Use **`@pytest.mark.django_db`** when the database is touched.
- Prefer exercising the **library** through patterns a consumer project would use (management commands, services, URLs) rather than only importing internals without integration context.

## Security

- Do not commit API keys, Metronome bearer tokens, or production `SECRET_KEY` values.
- The example `SECRET_KEY` in `example/example_site/settings.py` is the stock **insecure development** value from `startproject` — replace before any real deployment.
