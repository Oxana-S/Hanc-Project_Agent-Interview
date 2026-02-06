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
	@echo "  SETUP"
	@echo "  -----"
	@echo "  make install          Create venv and install all dependencies"
	@echo "  make install-min      Install minimal deps (Python 3.14)"
	@echo ""
	@echo "  MODES"
	@echo "  -----"
	@echo "  make consultant       Run Consultant mode (CLI, DeepSeek)"
	@echo "  make maximum          Run Maximum mode (CLI, DeepSeek + Redis + PostgreSQL)"
	@echo "  make voice            Run Voice mode (start server + agent)"
	@echo "  make server           Run web server only (port 8000)"
	@echo "  make agent            Run voice agent only (LiveKit)"
	@echo ""
	@echo "  INFRASTRUCTURE"
	@echo "  --------------"
	@echo "  make infra-up         Start Redis + PostgreSQL via docker-compose"
	@echo "  make infra-down       Stop Redis + PostgreSQL"
	@echo "  make infra-status     Check Redis + PostgreSQL container status"
	@echo ""
	@echo "  TESTING"
	@echo "  -------"
	@echo "  make test             Run all unit tests (252 tests)"
	@echo "  make test-sim         Run test simulation (list available scenarios)"
	@echo "  make test-scenario    Run a specific scenario"
	@echo "                        usage: make test-scenario SCENARIO=auto_service"
	@echo "  make pipeline         Run pipeline: test scenario + review"
	@echo "                        usage: make pipeline SCENARIO=vitalbox"
	@echo ""
	@echo "  UTILITIES"
	@echo "  ---------"
	@echo "  make healthcheck      Check system health (env, deps, Redis, PostgreSQL)"
	@echo "  make test-deepseek    Test DeepSeek API connection"
	@echo "  make kill-port        Kill process on port 8000"
	@echo "  make logs             Tail all log files"
	@echo "  make clean            Remove output/ and logs/"
	@echo ""

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
#  MODES
# ============================================================================

.PHONY: consultant maximum voice server agent

consultant: ## Run Consultant mode (CLI, DeepSeek)
	$(PYTHON) $(SCRIPTS)/consultant_demo.py

maximum: ## Run Maximum mode (CLI, DeepSeek + Redis + PostgreSQL)
	$(PYTHON) $(SCRIPTS)/demo.py

voice: ## Run Voice mode (start server + agent in parallel)
	@echo "--- Starting Voice mode ---"
	@echo "    Server: http://localhost:8000"
	@echo "    Agent:  LiveKit voice agent"
	@echo ""
	$(PYTHON) $(SCRIPTS)/run_server.py &
	@sleep 2
	$(PYTHON) $(SCRIPTS)/run_voice_agent.py

server: ## Run web server only (port 8000)
	$(PYTHON) $(SCRIPTS)/run_server.py

agent: ## Run voice agent only (LiveKit)
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

test: ## Run all unit tests (252 tests)
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

.PHONY: healthcheck test-deepseek kill-port logs clean

healthcheck: ## Check system health (env, deps, Redis, PostgreSQL)
	$(PYTHON) $(SCRIPTS)/healthcheck.py

test-deepseek: ## Test DeepSeek API connection
	$(PYTHON) $(SCRIPTS)/test_deepseek_api.py

kill-port: ## Kill process on port 8000
	@bash $(SCRIPTS)/kill_8000.sh

logs: ## Tail all log files
	@tail -f logs/*.log 2>/dev/null || echo "No log files found in logs/"

clean: ## Remove output/ and logs/
	rm -rf output/ logs/
	@echo "Removed output/ and logs/"
