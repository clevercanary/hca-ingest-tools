# HCA Smart-Sync

Intelligent S3 data synchronization for HCA Atlas source datasets and integrated objects.

## Installation

Install using pipx (recommended):

```bash
pipx install hca-smart-sync
```

## Usage

The sync command requires two arguments:

1. **Atlas name** (e.g., `gut-v1`, `immune-v1`)
2. **File type**: either `source-datasets` or `integrated-objects`

### Basic Examples

```bash
# Sync source datasets for gut atlas (production)
hca-smart-sync sync gut-v1 source-datasets --profile my-profile

# Sync integrated objects for immune atlas
hca-smart-sync sync immune-v1 integrated-objects --profile my-profile

# Dry run to preview changes
hca-smart-sync sync gut-v1 source-datasets --profile my-profile --dry-run

```

### Available Options

- `--profile TEXT` - AWS profile to use
- `--dry-run` - Preview changes without uploading
- `--verbose` - Show detailed output
- `--force` - Force upload even if checksums match
- `--local-path TEXT` - Custom local directory (defaults to current directory)

### Getting Help

```bash
# Show all available commands
hca-smart-sync --help

# Show sync command options
hca-smart-sync sync --help

# Show version
hca-smart-sync --version
```

## Features

- **Smart synchronization** - Only uploads files with changed checksums
- **SHA256 verification** - Research-grade data integrity
- **Manifest generation** - Automatic upload manifests
- **Progress tracking** - Real-time upload progress
- **Environment support** - Separate prod and dev buckets
- **Dry run mode** - Preview changes before uploading

## Requirements

- Python 3.10+
- AWS CLI configured with appropriate profiles
- S3 access to HCA Atlas buckets
