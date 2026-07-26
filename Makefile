.PHONY: audit backup lint docker-build docker-up security-check

# ── Security ──────────────────────────────────────────────────────────────────

audit:  ## Run dependency vulnerability scans (pip-audit + npm audit)
	bash scripts/security-audit.sh

security-check: audit  ## Full security check

backup:  ## Backup database + config
	bash scripts/backup.sh

# ── Lint ──────────────────────────────────────────────────────────────────────

lint:  ## Ruff lint + type check
	ruff check . --fix
	pyright .

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
