# ============================================================================
#  Hanc.AI - Voice Interviewer Agent
#  Unified Makefile
# ============================================================================

SHELL := /bin/bash

# -- Paths -------------------------------------------------------------------
PYTHON   := ./venv/bin/python
PIP      := ./venv/bin/pip
PYTEST   := ./venv/bin/pytest
COMPOSE  := docker compose -f config/docker-compose.yml
SCRIPTS  := scripts

# -- Scenario (overridable) --------------------------------------------------
SCENARIO ?= vitalbox

# ============================================================================
#  HELP
# ============================================================================

.PHONY: help
help: ## Show all available commands
	@echo ""
	@echo "  Hanc.AI -- Voice Interviewer Agent"
	@echo "  ==================================="
	@echo ""
	@echo "  SERVICES (daemon mode — не занимают терминал)"
	@echo "  --------"
	@echo "  make start              Start server + agent (background)"
	@echo "  make stop               Stop all services"
	@echo "  make restart            Restart all services"
	@echo "  make status             Show process status"
	@echo "  make logs               Tail all logs"
	@echo ""
	@echo "  SETUP"
	@echo "  -----"
	@echo "  make install            Create venv and install all dependencies"
	@echo "  make install-min        Install minimal deps (Python 3.14)"
	@echo ""
	@echo "  FOREGROUND (для разработки — выводят логи в терминал)"
	@echo "  ----------"
	@echo "  make server             Run web server (foreground)"
	@echo "  make agent              Run voice agent (foreground)"
	@echo "  make consultant         Run Consultant mode (CLI demo)"
	@echo ""
	@echo "  INFRASTRUCTURE"
	@echo "  --------------"
	@echo "  make infra-up           Start Redis + PostgreSQL via docker-compose"
	@echo "  make infra-down         Stop Redis + PostgreSQL"
	@echo "  make infra-status       Check Redis + PostgreSQL container status"
	@echo ""
	@echo "  TESTING"
	@echo "  -------"
	@echo "  make test               Run all unit tests (1481 tests)"
	@echo "  make test-sim           Run test simulation (list scenarios)"
	@echo "  make test-scenario      Run a specific scenario"
	@echo "                          usage: make test-scenario SCENARIO=auto_service"
	@echo "  make pipeline           Run pipeline: test scenario + review"
	@echo "                          usage: make pipeline SCENARIO=vitalbox"
	@echo ""
	@echo "  UTILITIES"
	@echo "  ---------"
	@echo "  make test-deepseek      Test DeepSeek API connection"
	@echo "  make cleanup-rooms      List/delete LiveKit rooms"
	@echo "  make kill-all           Emergency kill all processes (SIGKILL)"
	@echo "  make clean              Remove output/ and logs/"
	@echo ""

# ============================================================================
#  SERVICES (daemon mode via hanc.sh)
# ============================================================================

.PHONY: start stop restart status logs kill-all

start: ## Start server + agent in background
	@bash $(SCRIPTS)/hanc.sh start

stop: ## Stop all services
	@bash $(SCRIPTS)/hanc.sh stop

restart: ## Restart all services
	@bash $(SCRIPTS)/hanc.sh restart

status: ## Show process status
	@bash $(SCRIPTS)/hanc.sh status

logs: ## Tail all log files
	@bash $(SCRIPTS)/hanc.sh logs

kill-all: ## Emergency kill all processes
	@bash $(SCRIPTS)/hanc.sh kill-all

# ============================================================================
#  SETUP
# ============================================================================

.PHONY: install install-min

install: ## Create venv and install all dependencies
	@echo "--- Creating virtual environment ---"
	python3 -m venv venv
	@echo "--- Installing dependencies ---"
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo ""
	@echo "Done. Activate with:  source venv/bin/activate"

install-min: ## Install minimal dependencies (Python 3.14)
	@echo "--- Creating virtual environment (minimal) ---"
	python3 -m venv venv
	@echo "--- Installing minimal dependencies ---"
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-minimal.txt
	@echo ""
	@echo "Done. Activate with:  source venv/bin/activate"

# ============================================================================
#  FOREGROUND (development)
# ============================================================================

.PHONY: consultant server agent

consultant: ## Run Consultant mode (CLI, DeepSeek)
	$(PYTHON) $(SCRIPTS)/consultant_demo.py

server: ## Run web server only (foreground, port 8000)
	$(PYTHON) $(SCRIPTS)/run_server.py

agent: ## Run voice agent only (foreground, LiveKit)
	$(PYTHON) $(SCRIPTS)/run_voice_agent.py

# ============================================================================
#  INFRASTRUCTURE
# ============================================================================

.PHONY: infra-up infra-down infra-status

infra-up: ## Start Redis + PostgreSQL via docker-compose
	$(COMPOSE) up -d redis postgres
	@echo ""
	@echo "Redis:      localhost:6379"
	@echo "PostgreSQL: localhost:5432"

infra-down: ## Stop Redis + PostgreSQL
	$(COMPOSE) down

infra-status: ## Check Redis + PostgreSQL container status
	$(COMPOSE) ps

# ============================================================================
#  TESTING
# ============================================================================

.PHONY: test test-sim test-scenario pipeline

test: ## Run all unit tests (1481 tests)
	$(PYTEST) tests/ -m "unit or not integration"

test-sim: ## Run test simulation (list available scenarios)
	$(PYTHON) $(SCRIPTS)/run_test.py --list

test-scenario: ## Run a specific scenario (SCENARIO=auto_service)
	$(PYTHON) $(SCRIPTS)/run_test.py $(SCENARIO)

pipeline: ## Run pipeline: test scenario + review (SCENARIO=vitalbox)
	$(PYTHON) $(SCRIPTS)/run_pipeline.py $(SCENARIO)

# ============================================================================
#  UTILITIES
# ============================================================================

.PHONY: test-deepseek cleanup-rooms clean

test-deepseek: ## Test DeepSeek API connection
	$(PYTHON) $(SCRIPTS)/test_deepseek_api.py

cleanup-rooms: ## List/delete LiveKit rooms
	$(PYTHON) $(SCRIPTS)/cleanup_rooms.py

clean: ## Remove output/ and logs/
	rm -rf output/ logs/
	@echo "Removed output/ and logs/"
