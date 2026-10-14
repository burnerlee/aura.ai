# Copyright (c) 2026 DevRev Inc. All rights reserved.

.PHONY: help setup venv install install-dev env mongo-up mongo-down mongo-logs mongo-reset \
	ping connectors scrape-substack discover reload-clean list-docs lint test clean

# Prefer 3.11+ when available (macOS system python is often 3.9).
PYTHON ?= $(shell command -v python3.12 || command -v python3.11 || command -v python3)
VENV ?= .venv
BIN := $(VENV)/bin
PIP := $(BIN)/pip
PY := $(BIN)/python
SCRAPER := $(BIN)/scraper

# Defaults for scrape/discover targets
SOURCE ?= platformer
LIMIT ?= 10
PER_CATEGORY ?= 5
POSTS ?= 3
TIER ?= rising

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: env venv install mongo-up ## Full local setup (env, venv, deps, MongoDB)
	@$(MAKE) ping
	@echo "Setup complete. Try: make scrape-substack SOURCE=platformer LIMIT=5"

venv: ## Create Python virtualenv
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@$(PIP) install --upgrade pip setuptools wheel

install: venv ## Install package + runtime deps
	@$(PIP) install -e .

install-dev: venv ## Install package + dev deps
	@$(PIP) install -e ".[dev]"

env: ## Copy .env.example → .env if missing
	@test -f .env || cp .env.example .env
	@echo "Using .env"

mongo-up: ## Start MongoDB via Docker Compose
	docker compose up -d mongodb
	@echo "Waiting for MongoDB health..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		docker compose ps --status running | grep -q content-scraper-mongo && \
		docker inspect --format='{{.State.Health.Status}}' content-scraper-mongo 2>/dev/null | grep -q healthy && break; \
		sleep 2; \
	done
	@echo "MongoDB is up on port $${MONGO_PORT:-27017}"

mongo-down: ## Stop MongoDB
	docker compose down

mongo-logs: ## Tail MongoDB logs
	docker compose logs -f mongodb

mongo-reset: ## Stop MongoDB and wipe volume data
	docker compose down -v

ping: ## Ping MongoDB through the app
	@$(SCRAPER) mongo-ping

connectors: ## List registered connectors
	@$(SCRAPER) connectors

scrape-substack: ## Scrape a Substack publication (SOURCE=handle LIMIT=N)
	@$(SCRAPER) scrape substack $(SOURCE) --limit $(LIMIT)

discover: ## Discover top blogs and scrape their posts (PER_CATEGORY / POSTS / TIER)
	@$(SCRAPER) discover substack --per-category $(PER_CATEGORY) --tier $(TIER) --posts $(or $(POSTS),3)

reload-clean: ## Wipe posts + discover sample categories and scrape articles
	@$(SCRAPER) mongo-reset --yes
	@$(SCRAPER) discover substack --per-category 2 --tier $(TIER) \
		-c technology -c business -c culture -c finance -c science \
		--posts $(or $(POSTS),2)
	@$(SCRAPER) list-docs --limit 8

list-docs: ## List scraped documents from MongoDB
	@$(SCRAPER) list-docs --source substack --limit $(LIMIT)

lint: ## Run ruff
	@$(BIN)/ruff check src

test: ## Run tests
	@$(BIN)/pytest -q

clean: ## Remove venv and caches
	rm -rf $(VENV) .pytest_cache .ruff_cache dist build *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
