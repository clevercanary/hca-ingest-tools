# HCA Smart-Sync

Intelligent S3 synchronization for HCA Atlas data.

## Installation

```bash
cd smart-sync
poetry install
```

## Usage

```bash
# Basic sync
poetry run hca-smart-sync sync gut-v1 --profile my-profile

# Dry run
poetry run hca-smart-sync sync gut-v1 --profile my-profile --dry-run

# Development environment
poetry run hca-smart-sync sync gut-v1 --profile my-profile --environment dev
```

## Development

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src

# Format code
poetry run black src tests

# Type checking
poetry run mypy src
```

## Features

- SHA256 checksum-based synchronization
- Manifest-driven uploads
- AWS CLI integration with progress display
- Environment-based bucket selection
- Interactive upload confirmation
- Research-grade data integrity verification

## Configuration

The tool supports environment-based bucket selection:
- `prod` (default): `hca-atlas-tracker-data`
- `dev`: `hca-atlas-tracker-data-dev`

## Requirements

- Python 3.10+
- AWS CLI configured with appropriate profiles
- Poetry for dependency management
