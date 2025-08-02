# HCA Ingest Tools - Monorepo Makefile
# Convenience commands for working with multiple packages

.PHONY: help install-all test-all clean-all lint-all format-all

help: ## Show this help message
	@echo "HCA Ingest Tools - Monorepo Commands"
	@echo "===================================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Installation commands
install-all: ## Install all packages
	@echo "📦 Installing all packages..."
	cd smart-sync && poetry install
	@echo "✅ All packages installed"

install-smart-sync: ## Install smart-sync package only
	@echo "📦 Installing smart-sync..."
	cd smart-sync && poetry install
	@echo "✅ smart-sync installed"

# Testing commands
test-all: ## Run tests for all packages
	@echo "🧪 Running tests for all packages..."
	poetry run pytest
	@echo "✅ All tests completed"

test-smart-sync: ## Run tests for smart-sync only
	@echo "🧪 Running smart-sync tests..."
	poetry run pytest
	@echo "✅ smart-sync tests completed"

test-smart-sync-cov: ## Run smart-sync tests with coverage
	@echo "🧪 Running smart-sync tests with coverage..."
	poetry run pytest --cov=src --cov-report=term-missing
	@echo "✅ smart-sync tests with coverage completed"

# Code quality commands
lint-all: ## Run linting for all packages
	@echo "🔍 Running linting for all packages..."
	poetry run ruff check src tests
	poetry run mypy src
	@echo "✅ All linting completed"

format-all: ## Format code for all packages
	@echo "🎨 Formatting code for all packages..."
	poetry run black src tests
	poetry run ruff check --fix src tests
	@echo "✅ All formatting completed"

# Cleanup commands
clean-all: ## Clean all build artifacts
	@echo "🧹 Cleaning all packages..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage coverage.xml htmlcov/
	@echo "✅ All packages cleaned"

# Development commands
dev-smart-sync: ## Set up smart-sync for development
	@echo "🛠️  Setting up smart-sync for development..."
	poetry install --with dev
	@echo "✅ smart-sync development setup complete"

# Package-specific shortcuts
smart-sync-cli: ## Run smart-sync CLI (pass args with ARGS="...")
	poetry run hca-smart-sync $(ARGS)

# Status commands
status: ## Show status of all packages
	@echo "📊 Package Status"
	@echo "================"
	@echo ""
	@echo "📁 smart-sync/"
	poetry show --tree | wc -l | tr -d ' ') packages"
	@echo "  Tests: $$(find tests -name '*.py' | wc -l | tr -d ' ') test files"
	@echo "  Source: $$(find src -name '*.py' | wc -l | tr -d ' ') Python files"
