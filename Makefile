# Dùng: make test | lint | fmt | test-db | cov | venv
# Mặc định MOCK=1, không gọi live Shopee/Facebook.
VENV   ?= .venv
PY     := $(VENV)/bin/python
export MOCK ?= 1
DB_URL ?= postgresql+psycopg://cashback:cashback_dev@127.0.0.1:5433/cashback

.PHONY: venv test db-up test-db lint fmt cov sync-once settle-once run-once

venv:
	python3 -m venv $(VENV)
	$(PY) -m pip install -q -e "backend[dev]"

test:
	$(PY) -m pytest backend/tests

# Cần Postgres: docker compose -f infra/docker-compose.yml up -d db migrate seed
db-up:
	docker compose -f infra/docker-compose.yml up -d --build db migrate seed

test-db:
	DATABASE_URL=$(DB_URL) $(PY) -m pytest backend/tests/integration

lint:
	$(VENV)/bin/ruff check --config backend/pyproject.toml .

fmt:
	$(VENV)/bin/ruff format --config backend/pyproject.toml --check . || true

cov:
	$(VENV)/bin/coverage run --source=backend/app -m pytest backend/tests
	$(VENV)/bin/coverage report

# Đồng bộ đơn một lần (MOCK=1 mặc định: dùng fixture, không gọi Shopee). Cần: make db-up
sync-once:
	cd backend && DATABASE_URL=$(DB_URL) SUBID_SECRET=$${SUBID_SECRET:-dev-subid-secret-0123456789abcdef} ../$(PY) -m app.main_worker sync-once

# Chốt ví từ các đơn đã đồng bộ / làm cả hai bước
settle-once:
	cd backend && DATABASE_URL=$(DB_URL) SUBID_SECRET=$${SUBID_SECRET:-dev-subid-secret-0123456789abcdef} ../$(PY) -m app.main_worker settle-once

run-once:
	cd backend && DATABASE_URL=$(DB_URL) SUBID_SECRET=$${SUBID_SECRET:-dev-subid-secret-0123456789abcdef} ../$(PY) -m app.main_worker run-once
