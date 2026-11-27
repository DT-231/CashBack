# Dùng: make test | lint | fmt | test-db | cov | venv
# Mặc định MOCK=1, không gọi live Shopee/Facebook.
VENV   ?= .venv
PY     := $(VENV)/bin/python
export MOCK ?= 1
DB_URL ?= postgresql+psycopg://cashback:cashback_dev@127.0.0.1:5433/cashback

.PHONY: venv test test-db lint fmt cov

venv:
	python3 -m venv $(VENV)
	$(PY) -m pip install -q -e "backend[dev]"

# Bộ test hiện có (service cũ + codec sub_id). Sẽ gom về pytest ở bước 2.
test:
	$(PY) test_offline.py
	$(PY) test_make_link_regression.py
	PYTHONPATH=packages/core $(PY) -m unittest discover -s packages/core/tests

# Cần Postgres: docker compose -f infra/docker-compose.yml up -d db migrate seed
test-db:
	cd apps/api && DATABASE_URL=$(DB_URL) ../../$(PY) -m unittest discover -s tests

lint:
	$(VENV)/bin/ruff check --config backend/pyproject.toml .

fmt:
	$(VENV)/bin/ruff format --config backend/pyproject.toml --check . || true

cov:
	PYTHONPATH=packages/core $(VENV)/bin/coverage run --source=. -m unittest discover -s packages/core/tests
	$(VENV)/bin/coverage run -a --source=. test_make_link_regression.py
	$(VENV)/bin/coverage run -a --source=. test_offline.py
	$(VENV)/bin/coverage report --omit='test_*,*/tests/*,apps/*'
