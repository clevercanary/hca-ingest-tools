.PHONY: help install test test-all lint format type-check build clean dev-setup pre-commit-install pre-commit-run

# Default target
help:
	@echo "HCA Ingest Tools - Development Commands"
	@echo "======================================"
	@echo ""
	@echo "Setup Commands:"
	@echo "  install              Install dependencies with Poetry"
	@echo "  dev-setup            Complete development environment setup"
	@echo "  pre-commit-install   Install pre-commit hooks"
	@echo ""
	@echo "Testing Commands:"
	@echo "  test                 Run basic test suite"
	@echo "  test-all             Run complete test suite with coverage"
	@echo "  test-watch           Run tests in watch mode"
	@echo ""
	@echo "Code Quality Commands:"
	@echo "  lint                 Run linting with ruff"
	@echo "  format               Format code with ruff"
	@echo "  type-check           Run type checking with mypy"
	@echo "  pre-commit-run       Run all pre-commit hooks"
	@echo "  quality-check        Run all quality checks (lint + type + test)"
	@echo ""
	@echo "Build Commands:"
	@echo "  build                Build package with Poetry"
	@echo "  clean                Clean build artifacts"
	@echo ""
	@echo "Development Commands:"
	@echo "  run-sync             Run smart-sync CLI (example usage)"
	@echo "  shell                Open Poetry shell"

# Setup Commands
install:
	@echo "📦 Installing dependencies..."
	poetry install

dev-setup: install pre-commit-install
	@echo "🚀 Development environment setup complete!"
	@echo "Run 'make help' to see available commands"

pre-commit-install:
	@echo "🪝 Installing pre-commit hooks..."
	poetry run pre-commit install

# Testing Commands
test:
	@echo "🧪 Running basic test suite..."
	poetry run pytest tests/ -v

test-all:
	@echo "🧪 Running complete test suite with coverage..."
	poetry run pytest tests/ -v \
		--cov=src \
		--cov-report=term-missing \
		--cov-report=html \
		--cov-report=xml \
		--cov-fail-under=44
	@echo ""
	@echo "📊 Coverage report generated:"
	@echo "  - Terminal: Above"
	@echo "  - HTML: htmlcov/index.html"
	@echo "  - XML: coverage.xml"

test-watch:
	@echo "👀 Running tests in watch mode..."
	poetry run pytest-watch tests/ -- -v

# Code Quality Commands
lint:
	@echo "🔍 Running linting with ruff..."
	poetry run ruff check src tests
	@echo "✅ Linting complete"

format:
	@echo "🎨 Formatting code with ruff..."
	poetry run ruff format src tests
	@echo "✅ Formatting complete"

type-check:
	@echo "🔍 Running type checking with mypy..."
	poetry run mypy src
	@echo "✅ Type checking complete"

pre-commit-run:
	@echo "🪝 Running all pre-commit hooks..."
	poetry run pre-commit run --all-files

quality-check: lint type-check test-all
	@echo "✅ All quality checks passed!"

# Build Commands
build: clean
	@echo "🏗️  Building package..."
	poetry build
	@echo "📦 Package built successfully:"
	@ls -la dist/

clean:
	@echo "🧹 Cleaning build artifacts..."
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	@echo "✅ Clean complete"

# Development Commands
run-sync:
	@echo "🔄 Running smart-sync CLI (example)..."
	@echo "Usage: poetry run hca-smart-sync sync ATLAS BUCKET FOLDER [OPTIONS]"
	@echo "Example: poetry run hca-smart-sync sync gut-v1 my-bucket source-datasets --dry-run"

shell:
	@echo "🐚 Opening Poetry shell..."
	poetry shell

# CI/CD Commands (for GitHub Actions)
ci-test: install test-all lint type-check
	@echo "🚀 CI test suite complete"

ci-build: install build
	@echo "🚀 CI build complete"
