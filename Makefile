.PHONY: help ingest-stock etl-stock test validate migrate backfill setup

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Setup Python virtual environment
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

ingest-stock: ## Run stock ingestion: VPS → Bronze (SeaweedFS)
	python3 -m ingestion.stock.sync_vps_to_bronze

ingest-stock-r2: ## Run stock ingestion from R2: CF R2 → Bronze
	python3 -m ingestion.stock.sync_r2_to_bronze

etl-stock: ## Run stock ETL: Bronze → Silver → Gold
	python3 -m etl.orchestrator --source stock

etl-stock-silver: ## Run only Bronze → Silver
	python3 -m etl.stock.bronze_to_silver

etl-stock-gold: ## Run only Silver → Gold
	python3 -m etl.stock.silver_to_gold

test: ## Run all tests
	python3 -m pytest tests/ -v

validate: ## Validate Bronze data integrity
	python3 scripts/validate_bronze.py

migrate: ## Run Alembic migrations (Gold zone)
	cd gold && alembic upgrade head

migrate-new: ## Create new migration: make migrate-new MSG="description"
	cd gold && alembic revision --autogenerate -m "$(MSG)"

backfill: ## Backfill historical data
	python3 scripts/backfill.py
