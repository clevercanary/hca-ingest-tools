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

### Option 1: Install with pipx (Recommended)
```bash
pipx install hca-ingest-tools
```

### Option 2: Install with Poetry (Development)
```bash
git clone https://github.com/your-org/hca-ingest-tools.git
cd hca-ingest-tools
poetry install
```

### Prerequisites
- **AWS CLI v2.27.60+** (install via Homebrew: `brew install awscli`)
- **Python 3.8+**
- **Valid AWS credentials** with S3 access

## Quick Start

### 1. Configure AWS Credentials
```bash
# Configure your AWS profile
aws configure --profile your-profile-name

# Or use environment variables
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
export AWS_DEFAULT_REGION=us-east-1
```

### 2. Basic Upload
```bash
# Navigate to your data directory
cd /path/to/your/h5ad/files

# Run sync with required arguments
hca-smart-sync gut-v1 --profile your-profile-name --environment prod

# Or specify a different directory
hca-smart-sync gut-v1 --profile your-profile-name --environment dev --local-path /data/gut/
```

## Command Reference

### `hca-smart-sync sync`

Upload .h5ad files to S3 with checksum-based synchronization.

```bash
hca-smart-sync ATLAS [OPTIONS]
```

**Arguments:**
- `ATLAS`: Atlas name (e.g., `gut-v1`, `immune-v1`, `adipose-v1`)

**Required Options:**
- `--profile NAME`: AWS profile to use (required)

**Optional Arguments:**
- `--environment ENV`: Target environment (`dev` or `prod`, default: `prod`)
- `--local-path PATH`: Directory to scan for files (default: current directory)
- `--dry-run`: Show what would be uploaded without uploading
- `--force`: Upload all files without confirmation

**Examples:**
```bash
# Basic upload to production
hca-smart-sync gut-v1 --profile my-profile

# Upload to development environment
hca-smart-sync gut-v1 --profile my-profile --environment dev

# Dry run to preview changes
hca-smart-sync gut-v1 --profile my-profile --dry-run

# Upload from specific directory
hca-smart-sync immune-v1 --profile my-profile --local-path /data/immune/batch1

# Force upload without confirmation
hca-smart-sync adipose-v1 --profile my-profile --force
```

### `hca-smart-sync config-show`

Display current configuration settings.

```bash
hca-smart-sync config-show [--profile NAME]
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
- **Unchanged files**: Matching SHA256 checksum (skipped)

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

## Configuration

### AWS Profile Configuration
```bash
# Configure a named profile
aws configure --profile hca-production
AWS Access Key ID: YOUR_ACCESS_KEY
AWS Secret Access Key: YOUR_SECRET_KEY
Default region name: us-east-1
Default output format: json
```

### Environment Variables
```bash
export AWS_PROFILE=hca-production
export AWS_DEFAULT_REGION=us-east-1
```

## File Structure

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

## Troubleshooting

### Common Issues

#### 1. AWS Credentials Not Found
```
Error: Unable to locate credentials
```
**Solution**: Configure AWS credentials or specify profile:
```bash
aws configure --profile your-profile
# or
export AWS_PROFILE=your-profile
```

#### 2. S3 Access Denied
```
Error: Access denied to bucket 'your-bucket'
```
**Solution**: Verify your IAM permissions allow:
- `s3:ListBucket` on the bucket
- `s3:GetObject` and `s3:PutObject` on objects
- `s3:PutObjectMetadata` for checksum storage

#### 3. No .h5ad Files Found
```
No .h5ad files found in directory
```
**Solution**: 
- Check you're in the correct directory
- Use `--local-path` to specify the data directory
- Verify files have `.h5ad` extension

#### 4. Upload Interrupted
If upload is interrupted (Ctrl+C), you'll have:
- Local manifest file with intended uploads
- Some files may be partially uploaded
- Re-run the same command to resume (smart-sync will skip completed files)

### Debug Mode
For detailed logging, set environment variable:
```bash
export HCA_DEBUG=1
hca-smart-sync sync ...
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
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": "arn:aws:s3:::your-bucket"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:PutObjectMetadata"
      ],
      "Resource": "arn:aws:s3:::your-bucket/your-atlas/*"
    }
  ]
}
```

## Support

- **Documentation**: [GitHub Wiki](https://github.com/your-org/hca-ingest-tools/wiki)
- **Issues**: [GitHub Issues](https://github.com/your-org/hca-ingest-tools/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/hca-ingest-tools/discussions)

## Related Tools

- **HCA Validation Tools**: Data validation and quality checks
- **HCA Atlas Tracker**: Submission tracking and status management
- **AWS CLI**: Underlying upload engine
