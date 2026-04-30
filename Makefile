.PHONY: test lint fmt check migrate runserver install-hooks pre-commit

test:
	poetry run pytest

lint:
	poetry run ruff check src tests example

fmt:
	poetry run ruff format src tests example

# Mirrors CI (pre-commit + pytest).
check: pre-commit test

# One-time per clone: registers git hooks (commit + push).
install-hooks:
	poetry run pre-commit install --install-hooks -t pre-commit -t pre-push

# Same checks as CI (only runs on git-tracked files; git add new files first).
pre-commit:
	poetry run pre-commit run --all-files

migrate:
	poetry run python example/manage.py migrate

runserver:
	poetry run python example/manage.py runserver
