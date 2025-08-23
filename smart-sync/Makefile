# HCA Smart-Sync - Development Makefile
# Convenience commands for smart-sync development

.PHONY: help install test test-cov lint format clean dev cli status build package

help: ## Show this help message
	@echo "HCA Smart-Sync - Development Commands"
	@echo "===================================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Installation commands
install: ## Install dependencies
	@echo "📦 Installing smart-sync..."
	poetry install
	@echo "✅ Installation completed"

dev: ## Set up for development (with dev dependencies)
	@echo "🛠️  Setting up for development..."
	poetry install --with dev
	@echo "✅ Development setup complete"

# Testing commands
test-all: ## Run tests
	@echo "🧪 Running tests..."
	poetry run pytest
	@echo "✅ Tests completed"

test-cov: ## Run tests with coverage
	@echo "🧪 Running tests with coverage..."
	poetry run pytest --cov=src --cov-report=term-missing
	@echo "✅ Tests with coverage completed"

# Code quality commands
lint: ## Run linting
	@echo "🔍 Running linting..."
	poetry run ruff check src tests
	poetry run mypy src
	@echo "✅ Linting completed"

format: ## Format code
	@echo "🎨 Formatting code..."
	poetry run black src tests
	poetry run ruff check --fix src tests
	@echo "✅ Formatting completed"

# Cleanup commands
clean: ## Clean build artifacts
	@echo "🧹 Cleaning build artifacts..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage coverage.xml htmlcov/
	rm -rf dist/ build/
	@echo "✅ Cleanup completed"

# Build commands
build: ## Build wheel and source distribution
	@echo "🔨 Building distribution packages..."
	poetry build
	@echo "✅ Build completed - artifacts in dist/"
	@ls -la dist/

package: clean build ## Clean and build fresh distribution packages
	@echo "📦 Fresh package build completed"

# CLI commands
cli: ## Run smart-sync CLI (pass args with ARGS="...")
	poetry run hca-smart-sync $(ARGS)

# Status commands
status: ## Show project status
	@echo "📊 Smart-Sync Status"
	@echo "==================="
	@echo ""
	@echo "Dependencies: $$(poetry show | wc -l | tr -d ' ') packages"
	@echo "Tests: $$(find tests -name '*.py' | wc -l | tr -d ' ') test files"
	@echo "Source: $$(find src -name '*.py' | wc -l | tr -d ' ') Python files"
	@echo ""
