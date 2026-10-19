# ---- InsolvencyHub ---------------------------------------------------------
SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

PROJECT      ?= insolvencyhub
API_SERVICE  ?= api
HEALTH_PATH  ?= /health
ENV_FILE     ?= .env
-include $(ENV_FILE)
export COMPOSE_PROJECT_NAME ?= $(PROJECT)
API_HOST_PORT ?= 20500
EXTRA_HOST_PORTS ?=
COMPOSE      := docker compose --env-file $(ENV_FILE)

.PHONY: help setup check-deps env check-ports build up wait migrate urls down logs ps test lint fmt typecheck shell seed check-migrations clean local-install local-test local-lint

help: ## Список команд
	@awk 'BEGIN{FS=":.*##"} /^[a-zA-Z_-]+:.*##/{printf "  \033[36m%-14s\033[0m %s\n",$$1,$$2}' $(MAKEFILE_LIST)

setup: check-deps env check-ports build up wait migrate urls ## Полная установка с нуля одной командой

check-deps: ## Проверить docker и docker compose v2
	@command -v docker >/dev/null || { echo "ERROR: docker не установлен"; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "ERROR: docker daemon недоступен (запущен? права на сокет?)"; exit 1; }
	@docker compose version >/dev/null 2>&1 || { echo "ERROR: нужен docker compose v2"; exit 1; }

env: ## Создать .env из .env.example (если нет) и сгенерировать секреты
	@if [ -f $(ENV_FILE) ]; then echo ".env уже есть — не трогаю"; else \
	  cp .env.example $(ENV_FILE); \
	  bash scripts/gen_secrets.sh $(ENV_FILE); \
	  echo ".env создан, секреты сгенерированы"; fi

check-ports: ## Проверить, что хост-порты свободны
	@for p in $(API_HOST_PORT) $(EXTRA_HOST_PORTS); do \
	  if [ -z "$$p" ]; then continue; fi; \
	  if (exec 3<>/dev/tcp/127.0.0.1/$$p) 2>/dev/null; then \
	    if ! $(COMPOSE) ps --format '{{.Publishers}}' 2>/dev/null | grep -q ":$$p->"; then \
	      echo "ERROR: порт $$p занят другим процессом. Освободите его или задайте другой в .env (см. *_HOST_PORT)"; exit 1; fi; \
	  fi; done; echo "Порты свободны"

build: ## Собрать образы
	$(COMPOSE) build

up: ## Поднять стек в фоне
	$(COMPOSE) up -d

wait: ## Дождаться healthy и ответа health-эндпоинта
	@for i in $$(seq 1 60); do \
	  curl -fsS http://127.0.0.1:$(API_HOST_PORT)$(HEALTH_PATH) >/dev/null 2>&1 && { echo "API healthy"; exit 0; }; sleep 2; done; \
	  echo "ERROR: API не ответил за 120 с"; $(COMPOSE) ps; $(COMPOSE) logs --tail=80 $(API_SERVICE); exit 1

migrate: ## Применить миграции
	$(COMPOSE) run --rm migrate

urls: ## Показать адреса
	@echo "API:     http://127.0.0.1:$(API_HOST_PORT)"
	@echo "Docs:    http://127.0.0.1:$(API_HOST_PORT)/docs"
	@echo "Health:  http://127.0.0.1:$(API_HOST_PORT)$(HEALTH_PATH)"

down: ## Остановить стек (данные сохраняются)
	$(COMPOSE) down

logs: ## Логи (make logs s=api)
	$(COMPOSE) logs -f --tail=200 $(s)

ps: ## Статус сервисов
	$(COMPOSE) ps

test: ## Тесты в контейнере на Postgres+Redis
	$(COMPOSE) --profile test run --rm --build test

lint: ## ruff check + format --check
	$(COMPOSE) --profile test run --rm --no-deps test sh -c "ruff check . && ruff format --check ."

fmt: ## ruff format + ruff check --fix
	$(COMPOSE) --profile test run --rm --no-deps --user "$$(id -u):$$(id -g)" -v "$$PWD":/app test sh -c "ruff format . && ruff check --fix ."

typecheck: ## mypy (строгий режим)
	$(COMPOSE) --profile test run --rm --no-deps test sh -c "mypy src"

shell: ## Shell в контейнере API
	$(COMPOSE) exec $(API_SERVICE) sh

seed: ## Демо-данные
	$(COMPOSE) run --rm api python scripts/seed_demo.py

check-migrations: ## alembic check
	$(COMPOSE) run --rm api alembic check

clean: ## Остановить и удалить контейнеры, тома и образы ЭТОГО проекта
	$(COMPOSE) --profile '*' down -v --remove-orphans --rmi local

# ---- Host targets (нужен uv на машине) ------------------------------------
local-install: ## uv sync на хосте
	uv sync

local-test: ## pytest на хосте
	uv run pytest -q

local-lint: ## ruff на хосте
	uv run ruff check . && uv run ruff format --check .
