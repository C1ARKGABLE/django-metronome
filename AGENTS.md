# AGENTS.md — django-metronome

Instructions for humans and coding agents working in this repository.

## What this is

**django-metronome** is a **reusable Django app** (installable Python package) for integrating [Metronome](https://www.metronome.com/) billing. It layers on top of the official [`metronome-sdk`](https://pypi.org/project/metronome-sdk/); it does not replace it.

## Repository map

| Path | Role |
|------|------|
| [`src/django_metronome/`](src/django_metronome/) | **Published library** — models, views, URLs, webhooks, etc. go here. |
| [`example/`](example/) | **Dev-only** Django project created with `django-admin startproject`. Proves the app wires up; **not** shipped as the product API surface. Prefer Django management commands over hand-editing `manage.py` / `asgi.py` / `wsgi.py`. |
| [`tests/`](tests/) | **pytest-django** tests; `DJANGO_SETTINGS_MODULE` and `pythonpath` live in [`pyproject.toml`](pyproject.toml). |
| [`pyproject.toml`](pyproject.toml) | **Poetry** dependencies, **Ruff**, **pytest** configuration. |
| [`.pre-commit-config.yaml`](.pre-commit-config.yaml) | **Git hooks** — Ruff format + check (with `--fix`), whitespace/YAML guards; runs on **commit** and **push**. |
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | **CI** — same as `make pre-commit` + `pytest` on push/PR. |
| [`README.md`](README.md) | User-facing overview and install story. |

External references agents should use when implementing Metronome behavior:

- [Metronome docs](https://docs.metronome.com/guides/get-started/home)
- [Metronome API](https://docs.metronome.com/api)
- [Django reusable apps](https://docs.djangoproject.com/en/stable/intro/reusable-apps/)
- [Django logging](https://docs.djangoproject.com/en/stable/topics/logging/)

## Environment

- **Python:** 3.12 or 3.13 only (`requires-python` in `pyproject.toml`; 3.14 when Django supports it).
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
- **Metronome HTTP:** When API work lands, use **`metronome-sdk`** — do not invent raw HTTP clients for Metronome in this repo.
- **Payments:** Card capture / SCA / PSP flows are **out of scope**; document boundaries in PRs if touching billing UX.

## Tests

- Add new tests under [`tests/`](tests/) as `test_*.py`.
- Use **`@pytest.mark.django_db`** when the database is touched.
- Prefer testing the **library** through URL includes / views wired like a consumer project, mirroring [`tests/test_hello.py`](tests/test_hello.py).

## Security

- Do not commit API keys, Metronome bearer tokens, or production `SECRET_KEY` values.
- The example `SECRET_KEY` in `example/example_site/settings.py` is the stock **insecure development** value from `startproject` — replace before any real deployment.
