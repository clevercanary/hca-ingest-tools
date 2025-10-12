# HCA S3 Sync User Guide

## Overview

HCA S3 Sync is an S3 synchronization tool for uploading biological data (.h5ad files) to Human Cell Atlas infrastructure. It provides:

- **Checksum-based comparison** using SHA256 (not file size)
- **Manifest-driven uploads** with submission workflow
- **Data integrity verification** with end-to-end checksums
- **AWS CLI integration** for reliable multipart uploads
- **AWS Transfer Acceleration** for faster international uploads
- **Interactive confirmation** with detailed upload plans

## Installation

### Install with pipx (Recommended)

```bash
pipx install hca-smart-sync
```

### Prerequisites

- **AWS CLI v2.27.60+** (install via Homebrew: `brew install awscli`)
- **Valid AWS credentials** with S3 access

## Quick Start

### 1. Configure AWS Credentials

```bash
# Configure your AWS profile
aws configure --profile your-profile-name
# Follow the on-screen prompts to enter:
#   AWS Access Key ID
#   AWS Secret Access Key
#   Default region: us-east-1 (required)
#   Default output format: json
```

### 2. Set Up Smart-Sync Defaults (Recommended)

```bash
# Initialize config with your default profile and atlas
hca-smart-sync config init
# Enter: AWS profile name
# Enter: Default atlas (e.g., gut-v1)

# View your config
hca-smart-sync config show
```

### 3. Basic Upload

```bash
# Navigate to your data directory
cd /path/to/your/h5ad/files

# Atlas first, then file type
hca-smart-sync sync gut-v1 source-datasets --profile your-profile-name

# Or use config defaults (no atlas or profile needed)
hca-smart-sync sync source-datasets

# Or specify a different directory
hca-smart-sync sync gut-v1 source-datasets --local-path /data/gut/
```

## Command Reference

### `hca-smart-sync config init`

Initialize or update configuration with default values.

```bash
hca-smart-sync config init
```

**Interactive prompts:**
- AWS profile name (leave empty to keep current)
- Default atlas name (leave empty to keep current)

**Example:**
```bash
hca-smart-sync config init
# AWS profile [current: excira]: my-profile
# Default atlas [current: gut-v1]: immune-v1
```

### `hca-smart-sync config show`

Display current configuration.

```bash
hca-smart-sync config show
```

### `hca-smart-sync sync`

Upload .h5ad files to S3 with checksum-based synchronization.

```bash
hca-smart-sync sync [ATLAS] FILE_TYPE [OPTIONS]
```

**Arguments (flexible order):**

- `ATLAS`: Atlas name (e.g., `gut-v1`, `immune-v1`) - optional if set in config
- `FILE_TYPE`: `source-datasets` or `integrated-objects` - **always required**

**The tool intelligently detects which argument is which:**
- If first arg is `source-datasets` or `integrated-objects`, it's treated as file type (atlas from config)
- Otherwise, first arg is atlas, second arg must be file type

**Options:**

- `--profile NAME`: AWS profile to use (uses config default if not specified)
- `--local-path PATH`: Directory to scan for files (default: current directory)
- `--dry-run`: Show what would be uploaded without uploading
- `--force`: Upload all files even if unchanged
- `--verbose`: Show detailed output
- `--environment [prod|dev]`: Target environment (default: prod)

**Examples:**

```bash
# Atlas first, file type second
hca-smart-sync sync gut-v1 source-datasets --profile my-profile

# File type only (uses config for atlas and profile)
hca-smart-sync sync source-datasets

# Upload integrated objects with config defaults
hca-smart-sync sync integrated-objects

# Override config atlas but use config profile
hca-smart-sync sync immune-v1 source-datasets

# Dry run to preview changes
hca-smart-sync sync gut-v1 source-datasets --dry-run

# Upload from specific directory
hca-smart-sync sync immune-v1 source-datasets --local-path /data/immune/batch1

# Force upload even for unchanged files
hca-smart-sync sync adipose-v1 integrated-objects --force

# Upload to dev environment
hca-smart-sync sync gut-v1 source-datasets --environment dev
```

## How It Works

### 1. File Scanning

- Scans specified directory for `.h5ad` files
- Calculates SHA256 checksum for each file
- Displays found files with sizes

### 2. S3 Comparison

- Checks each file against S3 using `source-sha256` metadata
- **New files**: Not found in S3
- **Changed files**: Different SHA256 checksum
- **Unchanged files**: Matching SHA256 checksum (skipped unless forced)

### 3. Upload Plan

- Shows interactive table with files to upload
- Displays file size, reason (new/changed), and SHA256 hash
- Prompts for user confirmation

### 4. Manifest Generation

- Creates manifest JSON with file metadata immediately after confirmation
- Saves manifest locally with human-readable timestamp filename
- Example: `manifest-2025-01-30-14-23-45-123.json`

### 5. File Upload

- Uploads files using AWS CLI with `source-sha256` metadata
- Shows real-time progress (speed, bytes transferred)
- Handles multipart uploads automatically

### 6. Manifest Upload

- Uploads manifest to S3 `manifests/` folder
- Triggers submission workflow in tracker application

## File System Structure

### S3 Bucket Layout

```
your-bucket/
├── bio-network/
│   └── atlas-name/
│       ├── source-datasets/     # Raw .h5ad files
│       ├── integrated-objects/  # Processed .h5ad files
│       └── manifests/          # Upload manifests (.json)
```

### Local Directory After Upload

```
your-data-directory/
├── file1.h5ad                           # Your data files
├── file2.h5ad
└── manifest-2025-01-30-14-23-45-123.json  # Local manifest copy
```

## Advanced Features

### Transfer Acceleration

If your S3 bucket has transfer acceleration enabled, smart-sync automatically uses the accelerated endpoint for faster international uploads.

### Integrity Verification

- **Local**: SHA256 calculated before upload
- **S3 Metadata**: `source-sha256` stored with each object
- **Verification**: Any tool can verify file integrity after download

### Manifest Format

```json
{
  "files": [
    {
      "filename": "sample1.h5ad",
      "path": "/full/path/to/sample1.h5ad",
      "size_bytes": 1234567890,
      "sha256": "abc123...",
      "last_modified": "2025-01-30T14:23:45Z"
    }
  ],
  "metadata": {
    "upload_destination": "s3://bucket/path/",
    "upload_timestamp": "2025-01-30T14:23:45.123Z",
    "tool": "hca-smart-sync",
    "version": "0.1.0"
  }
}
```

## Configuration Management

### Config File Location

The config file is stored at `~/.hca-smart-sync/config.yaml`

### Config File Format

```yaml
profile: my-aws-profile
atlas: gut-v1
```

### Precedence Rules

1. **CLI arguments** (highest priority)
2. **Config file defaults**
3. **Built-in defaults** (lowest priority)

For example:
```bash
hca-smart-sync sync immune-v1 --profile cli-profile
```
Will use `immune-v1` (from CLI) and `cli-profile` (from CLI), ignoring config values.

```bash
hca-smart-sync sync source-datasets
```
Will use `source-datasets` (from CLI) and load atlas + profile from config.

## Troubleshooting

### Common Issues

#### 1. Atlas Required Error

```
Error: Atlas is required.
```

**Solution**: Either provide atlas as argument or set default in config:

```bash
hca-smart-sync config init
# or
hca-smart-sync sync gut-v1 source-datasets
```

#### 2. AWS Credentials Not Found

```
Error: Unable to locate credentials
```

**Solution**: Configure AWS credentials or specify profile:

```bash
aws configure --profile your-profile
# or set default in config
hca-smart-sync config init
# or
export AWS_PROFILE=your-profile
```

#### 3. S3 Access Denied

```
Error: Access denied to bucket 'your-bucket'
```

**Solution**: Verify your IAM permissions allow:

- `s3:ListBucket` on the bucket
- `s3:GetObject` and `s3:PutObject` on objects
- `s3:PutObjectMetadata` for checksum storage

#### 4. No .h5ad Files Found

```
No .h5ad files found in directory
```

**Solution**:

- Check you're in the correct directory
- Use `--local-path` to specify the data directory
- Verify files have `.h5ad` extension

#### 5. Upload Interrupted

If upload is interrupted (Ctrl+C), you'll have:

- Local manifest file with intended uploads
- Some files may be partially uploaded
- Re-run the same command to resume (smart-sync will skip completed files)

### Debug Mode

For detailed logging, use the `--verbose` flag:

```bash
hca-smart-sync sync gut-v1 source-datasets --profile my-profile --verbose
```

### Performance Tips

1. **Use Transfer Acceleration** for international uploads
2. **Upload from same AWS region** when possible
3. **Stable internet connection** for large files
4. **AWS CLI v2.27.60+** for best performance

## Integration with HCA Infrastructure

### Submission Workflow

1. **Upload files** → S3 `source-datasets/` or `integrated-objects/`
2. **Upload manifest** → S3 `manifests/` folder
3. **Manifest triggers** → Tracker app creates submission record
4. **Tracker queues** → Validation workflow
5. **Validation results** → Status updates in tracker

### IAM Policy Requirements

Your IAM user/role needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::your-bucket"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:PutObjectMetadata"],
      "Resource": "arn:aws:s3:::your-bucket/your-atlas/*"
    }
  ]
}
```
