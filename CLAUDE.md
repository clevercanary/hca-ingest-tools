# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HCA Ingest Tools is a collection of tools for ingesting biological data into the Human Cell Atlas (HCA) infrastructure. The main component is **Smart-Sync**, an intelligent S3 synchronization tool for uploading biological data (.h5ad files) with manifest generation, integrity verification, and submission workflows.

## Build/Test/Lint Commands

All commands run from the `smart-sync/` directory using Poetry and the Makefile:

```bash
# Development setup
make install              # Install dependencies
make dev                  # Set up development environment

# Testing
make test-all             # Run all tests with pytest
make test-cov             # Run tests with coverage report
poetry run pytest tests/test_cli.py::TestSyncCommand::test_sync_success -v  # Run single test

# Code quality
make lint                 # Run ruff and mypy
make format               # Format with black and ruff

# Building
make build                # Build wheel and source distribution
make package              # Clean and build fresh
```

## Architecture

```
smart-sync/src/hca_smart_sync/
├── cli.py              # Typer CLI interface (sync, config init, config show)
├── sync_engine.py      # Core SmartSync class with S3 operations
├── config_manager.py   # YAML config (~/.hca-smart-sync/config.yaml)
├── checksum.py         # SHA256 verification utilities
├── manifest.py         # JSON manifest generation
└── config/
    └── __init__.py     # Pydantic models (Config, AWSConfig, S3Config, ManifestConfig)
```

**Key patterns:**
- SmartSync engine uses lazy S3 client initialization
- Configuration via Pydantic BaseSettings with `HCA_*` environment variable prefix
- CLI built with Typer framework, Rich console for output formatting

## Code Quality Standards

- **Strict typing**: MyPy strict mode enabled - all functions require full type annotations
- **Black**: 88 char line length, Python 3.10 target
- **Ruff**: Fast linter with strict rules
- **Tests**: pytest with fixtures, mocking via pytest-mock
