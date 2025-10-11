# HCA Smart-Sync

Intelligent S3 data synchronization for HCA Atlas source datasets and integrated objects.

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

## Installation

Install using pipx (recommended):

```bash
pipx install hca-smart-sync
```

## Quick Start

### First Time Setup

Configure default settings (optional but recommended):

```bash
hca-smart-sync config init
# Enter your default AWS profile and atlas name
```

### Basic Usage

```bash
# Sync source datasets for gut atlas
hca-smart-sync sync gut-v1 source-datasets --profile my-profile

# Sync integrated objects for immune atlas
hca-smart-sync sync immune-v1 integrated-objects --profile my-profile

# Dry run to preview changes
hca-smart-sync sync gut-v1 source-datasets --profile my-profile --dry-run
```

### Using Config Defaults

Once you've configured defaults, you can omit the atlas:

```bash
# File type only (uses config for atlas and profile)
hca-smart-sync sync source-datasets

# Or integrated objects
hca-smart-sync sync integrated-objects

# Override config atlas, use config profile
hca-smart-sync sync immune-v1 source-datasets
```

### Flexible Argument Order

The tool accepts arguments in two ways:

```bash
# Atlas first, then file type
hca-smart-sync sync gut-v1 source-datasets

# File type first (uses config for atlas)
hca-smart-sync sync source-datasets
```

**Note:** File type is always required - you must specify either `source-datasets` or `integrated-objects`.

### Available Options

- `--profile TEXT` - AWS profile to use (uses config default if not specified)
- `--dry-run` - Preview changes without uploading
- `--verbose` - Show detailed output
- `--force` - Force upload even if file content is unchanged
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
