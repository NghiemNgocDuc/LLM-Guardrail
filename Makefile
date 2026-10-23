.PHONY: audit backup lint test docker-build docker-up docker-logs docker-clean security-check db-migrate db-rollback dev-api dev-web help

# ── Security ──────────────────────────────────────────────────────────────────

audit:  ## Run dependency vulnerability scans (pip-audit + npm audit)
	bash scripts/security-audit.sh

security-check: audit  ## Full security check

backup:  ## Backup database + config
	bash scripts/backup.sh

# ── Lint ──────────────────────────────────────────────────────────────────────

lint:  ## Check Python application code and frontend types
	python -m ruff check app guardrails main.py grpc_gateway/server.py sdk/python examples
	npm run typecheck

test:  ## Run the backend test suite
	python -m pytest -q

# ── Docker ────────────────────────────────────────────────────────────────────

docker-build:  ## Build production images
	docker compose build --no-cache

docker-up:  ## Start all services
	docker compose up -d

docker-logs:  ## Tail logs
	docker compose logs -f

docker-clean:  ## Remove all volumes
	docker compose down -v

# ── DB ────────────────────────────────────────────────────────────────────────

db-migrate:  ## Run alembic migrations
	alembic upgrade head

db-rollback:  ## Undo last migration
	alembic downgrade -1

# ── Development ───────────────────────────────────────────────────────────────

dev-api:  ## Start API in dev mode
	uvicorn main:app --reload --host 0.0.0.0 --port 8000

dev-web:  ## Start frontend in dev mode
	npm run dev

# ── Help ──────────────────────────────────────────────────────────────────────

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
