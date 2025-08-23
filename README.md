# HCA Ingest Tools

A collection of tools for ingesting biological data into the Human Cell Atlas (HCA) infrastructure, including smart synchronization, manifest generation, and submission workflows.

## Overview

This repository contains tools that help researchers submit biological data to HCA atlas projects:

- **Smart-Sync**: Intelligent S3 synchronization with manifest generation and integrity verification
- **Upload Helpers**: Batch upload utilities and progress tracking
- **Submission Tools**: Workflow automation for data submission pipelines

## Project Structure

```
hca-ingest-tools/
├── smart-sync/
│   ├── docs/                    # User documentation
│   ├── src/
│   │   └── hca_smart_sync/      # Main sync tool
│   │       ├── config/          # Configuration management
│   │       ├── cli.py           # Command-line interface
│   │       ├── sync_engine.py   # Core sync logic
│   │       ├── manifest.py      # Manifest generation
│   │       └── checksum.py      # Integrity verification
│   ├── tests/                   # Test suite
│   └── pyproject.toml           # Poetry configuration
└── README.md                    # This file
```

## Installation

This project uses Poetry for dependency management. To install:

```bash
# Clone the repository
git clone https://github.com/your-org/hca-ingest-tools.git
cd hca-ingest-tools

# Install with Poetry
poetry install

# Or install globally with pipx (recommended for end users)
pipx install hca-ingest-tools
```

## Quick Start

### Smart-Sync Usage

```bash
# Sync local data to S3 with manifest generation
hca-smart-sync /path/to/local/data s3://bucket/bionetwork/atlas/source-datasets/

# Preview changes without uploading
hca-smart-sync --dry-run /path/to/local/data s3://bucket/bionetwork/atlas/source-datasets/

# Upload with custom manifest metadata
hca-smart-sync --metadata '{"study": "gut-atlas-v1", "submitter": "researcher@university.edu"}' \
  /path/to/local/data s3://bucket/gut/gut-v1/source-datasets/
```

## Features

### 🚀 Smart Synchronization
- **Intelligent diffing** - Only uploads changed files
- **Integrity verification** - SHA256 checksums for all files
- **Manifest generation** - Automatic submission metadata
- **Progress tracking** - Real-time upload progress
- **Resume capability** - Interrupted uploads can be resumed

### 🔒 Security & Compliance
- **AWS profile integration** - Uses your existing AWS credentials
- **IAM policy compliance** - Respects bucket access restrictions
- **Data integrity** - End-to-end checksum verification
- **Audit trails** - Complete upload history and manifests

### 🧬 Biological Data Focus
- **H5AD file support** - Optimized for biological data formats
- **Atlas structure** - Understands bionetwork/atlas/folder hierarchy
- **Metadata enrichment** - Biological context in manifests
- **Validation integration** - Works with hca-validation-tools

## Configuration

### AWS Setup

```bash
# Configure AWS profile (if not already done)
aws configure --profile your-profile-name

# Set default profile for HCA tools
export HCA_AWS_PROFILE=your-profile-name
```

### Tool Configuration

```bash
# Initialize configuration
hca-smart-sync --init

# Edit configuration file
vim ~/.config/hca-ingest-tools/config.yaml
```

## Integration with HCA Ecosystem

This tool integrates with the broader HCA infrastructure:

```
hca-validation-tools  →  Validates data quality
         ↓
hca-ingest-tools     →  Uploads validated data (this repo)
         ↓
hca-atlas-tracker    →  Tracks submitted data
```

### Workflow Integration

1. **Upload** with `hca-smart-sync` (this tool)
2. **Track** submission status in `hca-atlas-tracker`
3. **Validate** data with `hca-validation-tools`
4. **Monitor** validation results and processing

## Development

### Setup Development Environment

```bash
# Clone and setup
git clone https://github.com/clevercanary/hca-ingest-tools.git
cd hca-ingest-tools

# Install development dependencies
make dev

# Run tests
make test-all

# Run linting
make lint
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Run the test suite (`poetry run pytest`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: [docs/](smart-sync/docs/)
- **Issues**: [GitHub Issues](https://github.com/clevercanary/hca-ingest-tools/issues)

## Related Projects

- [hca-validation-tools](https://github.com/clevercanary/hca-validation-tools) - Data validation and quality tools
- [hca-atlas-tracker](https://github.com/clevercanary/hca-atlas-tracker) - Submission tracking and management
