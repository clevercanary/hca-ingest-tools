"""Smart sync engine for HCA data uploads."""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import boto3
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn

from hca_ingest.config import Config
from hca_ingest.smart_sync.checksum import ChecksumCalculator
from hca_ingest.smart_sync.manifest import ManifestGenerator


class SmartSync:
    """Smart synchronization engine for HCA data uploads."""
    
    def __init__(self, config: Config):
        """Initialize the sync engine."""
        self.config = config
        self.console = Console()
        self.checksum_calculator = ChecksumCalculator()
        self.manifest_generator = ManifestGenerator()
        
        # AWS clients will be created lazily to use current config
        self._s3_client = None
    
    @property
    def s3_client(self):
        """Get S3 client, creating it lazily with current config."""
        if self._s3_client is None:
            session = boto3.Session(profile_name=self.config.aws.profile)
            self._s3_client = session.client('s3', region_name=self.config.aws.region)
        return self._s3_client
    
    def _reset_aws_clients(self):
        """Reset AWS clients to pick up config changes."""
        self._s3_client = None
    
    def sync(
        self,
        local_path: Path,
        s3_path: str,
        dry_run: bool = False,
        verbose: bool = False,
        force: bool = False,
    ) -> Dict:
        """
        Perform smart sync of .h5ad files to S3.
        
        Args:
            local_path: Local directory to scan
            s3_path: S3 destination path
            dry_run: Show what would be uploaded without uploading
            verbose: Enable verbose output
            force: Force upload even if files haven't changed
            
        Returns:
            Dictionary with sync results
        """
        # Display banner
        self.console.print("\n[bold blue]" + "="*60 + "[/bold blue]")
        self.console.print("[bold blue]║" + "HCA Smart-Sync Tool".center(58) + "║[/bold blue]")
        self.console.print("[bold blue]" + "="*60 + "[/bold blue]")
        self.console.print()
        self.console.print(f"[bright_black]Local Path: {local_path}[/bright_black]")
        self.console.print(f"[bright_black]S3 Target: {s3_path}[/bright_black]")
        if dry_run:
            self.console.print()
            self.console.print("[bold]DRY RUN MODE - No files will be uploaded[/bold]")
        self.console.print()
        
        self.console.print("[bold blue]Step 1: Validating S3 access...[/bold blue]")
        
        # Step 0: Validate S3 access before proceeding
        if not self._validate_s3_access(s3_path):
            self.console.print("[red]S3 access validation failed. Cannot proceed with sync.[/red]")
            self.console.print("[yellow]Try using the correct AWS profile with --profile option[/yellow]")
            return {"files_uploaded": 0, "manifest_path": None, "error": "access_denied"}
        
        self.console.print("[bold blue]Step 2: Scanning local file system for .h5ad files...[/bold blue]")
        
        # Step 1: Scan for .h5ad files in current directory
        local_files = self._scan_local_files(local_path)
        
        if not local_files:
            self.console.print("[yellow]No .h5ad files found in directory[/yellow]")
            return {"files_uploaded": 0, "manifest_path": None}
        
        self.console.print("[bold blue]Step 3: Comparing with S3 (using SHA256 checksums)...[/bold blue]")
        
        # Step 2: Compare with S3 to determine what needs uploading
        files_to_upload = self._compare_with_s3(local_files, s3_path, force)
        
        if not files_to_upload:
            self.console.print("Found " + str(len(local_files)) + " .h5ad files - all up to date")
            return {"files_uploaded": 0, "manifest_path": None}
        
        # Sort files alphabetically once for consistent ordering throughout workflow
        files_to_upload = sorted(files_to_upload, key=lambda x: x['filename'])
        
        self.console.print("[bold blue]Step 4: Creating upload plan...[/bold blue]")
        
        # Step 3: Display upload plan (already sorted)
        self._display_upload_plan(files_to_upload, s3_path, dry_run)
        
        # Step 4.5: Get user confirmation (unless dry run or force)
        if not dry_run and not force:
            if not Confirm.ask("\nProceed with upload?"):
                return {"files_uploaded": 0, "manifest_path": None, "cancelled": True}
            self.console.print()  # Add blank line after confirmation
        
        # Step 4.5: Generate and save manifest locally first (before uploads)
        manifest_path = None
        if not dry_run:
            self.console.print("[bold blue]Step 5: Generating and saving manifest locally...[/bold blue]")
            manifest_path = self._generate_and_save_manifest_locally(files_to_upload, s3_path, local_path)
        
        # Step 5: Upload files using AWS CLI
        uploaded_files = []
        if not dry_run:
            self.console.print("[bold blue]Step 6: Uploading files...[/bold blue]")
            uploaded_files = self._upload_files(files_to_upload, s3_path)
        else:
            uploaded_files = files_to_upload  # For dry run reporting
        
        # Step 6: Upload manifest to S3 (if we have uploaded files)
        if uploaded_files and not dry_run and manifest_path:
            self.console.print("\n[bold blue]Step 7: Uploading manifest to S3...[/bold blue]")
            self._upload_manifest_to_s3(manifest_path, s3_path)
        
        return {
            "files_uploaded": len(uploaded_files),
            "manifest_path": manifest_path,
            "files": [f["local_path"].name for f in uploaded_files]
        }
    
    def _scan_local_files(self, local_path: Path) -> List[Dict]:
        """Scan for .h5ad files in the local directory."""
        local_files = []
        
        for file_path in local_path.glob("*.h5ad"):
            if file_path.is_file():
                # Calculate checksum
                with self.console.status(f"Calculating checksum for {file_path.name}..."):
                    checksum = self.checksum_calculator.calculate_sha256(file_path)
                
                local_files.append({
                    "local_path": file_path,
                    "filename": file_path.name,
                    "size": file_path.stat().st_size,
                    "checksum": checksum,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime)
                })
        
        return local_files
    
    def _compare_with_s3(self, local_files: List[Dict], s3_path: str, force: bool) -> List[Dict]:
        """Compare local files with S3 and determine what needs uploading."""
        files_to_upload = []
        bucket, prefix = self._parse_s3_path(s3_path)
        
        for local_file in local_files:
            s3_key = f"{prefix.rstrip('/')}/{local_file['filename']}"
            
            if force:
                files_to_upload.append({**local_file, "reason": "forced"})
                continue
            
            try:
                # Check if file exists in S3
                response = self.s3_client.head_object(Bucket=bucket, Key=s3_key)
                
                # Compare checksums if metadata exists
                s3_checksum = response.get('Metadata', {}).get('source-sha256')
                if s3_checksum and s3_checksum == local_file['checksum']:
                    continue  # File is identical, skip
                
                # File exists but has different checksum or no checksum metadata
                files_to_upload.append({**local_file, "reason": "changed"})
                
            except self.s3_client.exceptions.NoSuchKey:
                # File doesn't exist in S3 - this is normal for new files
                files_to_upload.append({**local_file, "reason": "new"})
            except Exception as e:
                # Only show warnings for actual errors (not 404s which are handled above)
                error_code = getattr(e, 'response', {}).get('Error', {}).get('Code', 'Unknown')
                if error_code not in ['NoSuchKey', '404']:
                    self.console.print(f"[yellow]Warning: Could not check {s3_key}: {e}[/yellow]")
                # Treat any access error as "new" to be safe
                files_to_upload.append({**local_file, "reason": "new"})
        
        return files_to_upload
    
    def _display_upload_plan(self, files_to_upload: List[Dict], s3_path: str, dry_run: bool):
        """Display the upload plan to the user."""
        action = "Would upload" if dry_run else "Will upload"
        
        self.console.print(f"\n[bold green]Upload Plan[/bold green]")
        
        table = Table(border_style="bright_black")
        table.add_column("File", style="bright_black")
        table.add_column("Size", style="bright_black")
        table.add_column("Reason", style="bright_black")
        table.add_column("SHA256", style="bright_black")
        
        total_size = 0
        for file_info in files_to_upload:
            size_mb = file_info['size'] / (1024 * 1024)
            total_size += file_info['size']
            
            table.add_row(
                file_info['filename'],
                f"{size_mb:.1f} MB",
                file_info['reason'],
                file_info['checksum'][:16] + "..."
            )
        
        self.console.print(table)
        
        total_mb = total_size / (1024 * 1024)
        self.console.print(f"\n[bold]{action} {len(files_to_upload)} files ({total_mb:.1f} MB total)[/bold]")
    
    def _upload_files(self, files_to_upload: List[Dict], s3_path: str) -> List[Dict]:
        """Upload files using AWS CLI."""
        uploaded_files = []
        bucket, prefix = self._parse_s3_path(s3_path)
        
        for file_info in files_to_upload:
            self.console.print()  # Add spacing before each upload
            try:
                s3_key = f"{prefix.rstrip('/')}/{file_info['filename']}"
                s3_url = f"s3://{bucket}/{s3_key}"
                
                # Build AWS CLI command
                cmd = [
                    "aws", "s3", "cp",
                    str(file_info['local_path']),
                    s3_url,
                    "--metadata", f"source-sha256={file_info['checksum']}",
                ]
                
                if self.config.aws.profile:
                    cmd.extend(["--profile", self.config.aws.profile])
                
                # Execute upload with live progress display
                # AWS CLI will show progress bars, transfer speed, and bytes transferred
                result = subprocess.run(cmd, check=True)
                
                uploaded_files.append(file_info)
                self.console.print(f"[green]Successfully uploaded: {file_info['filename']}[/green]")
                
            except subprocess.CalledProcessError as e:
                self.console.print(f"[red]Failed to upload {file_info['filename']}: {e}[/red]")
                raise
        
        return uploaded_files
    
    def _generate_and_save_manifest_locally(self, files_to_upload: List[Dict], s3_path: str, local_path: Path) -> str:
        """Generate and save manifest file locally."""
        
        # Generate manifest
        manifest = self.manifest_generator.generate_manifest(
            files=[f["local_path"] for f in files_to_upload],
            metadata={
                "upload_destination": s3_path,
                "upload_timestamp": datetime.utcnow().isoformat() + "Z",
                "tool": "hca-smart-sync",
                "version": "0.1.0"
            }
        )
        
        # Generate human-readable manifest filename
        manifest_filename = self.manifest_generator.generate_manifest_filename()
        # Save manifest in the same directory as the data files
        local_manifest_path = local_path / manifest_filename
        
        # Save manifest locally first
        self.manifest_generator.save_manifest(manifest, local_manifest_path)
        
        return str(local_manifest_path)
    
    def _upload_manifest_to_s3(self, manifest_path: str, s3_path: str):
        """Upload manifest to S3."""
        bucket, prefix = self._parse_s3_path(s3_path)
        # Replace last folder (source-datasets) with manifests
        manifest_prefix = "/".join(prefix.rstrip('/').split('/')[:-1] + ['manifests'])
        manifest_s3_url = f"s3://{bucket}/{manifest_prefix}/{manifest_path.split('/')[-1]}"
        
        try:
            cmd = [
                "aws", "s3", "cp",
                manifest_path,
                manifest_s3_url,
                "--profile", self.config.aws.profile
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            self.console.print(f"[green]Manifest uploaded: {manifest_s3_url}[/green]")
            
        except subprocess.CalledProcessError as e:
            self.console.print(f"[red]Failed to upload manifest: {e}[/red]")
            if e.stderr:
                self.console.print(f"[red]Error: {e.stderr}[/red]")
            raise
    
    def _parse_s3_path(self, s3_path: str) -> Tuple[str, str]:
        """Parse S3 path into bucket and prefix."""
        if not s3_path.startswith("s3://"):
            raise ValueError("S3 path must start with s3://")
        
        path_parts = s3_path[5:].split("/", 1)
        bucket = path_parts[0]
        prefix = path_parts[1] if len(path_parts) > 1 else ""
        
        return bucket, prefix
    
    def _validate_s3_access(self, s3_path: str) -> bool:
        """
        Validate that we have proper S3 access before attempting sync.
        
        Args:
            s3_path: S3 path to validate access for
            
        Returns:
            True if access is valid, False otherwise
        """
        try:
            bucket, prefix = self._parse_s3_path(s3_path)
            
            # Test basic bucket access by listing objects with a limit
            # This is a lightweight operation that tests both read permissions
            # and bucket existence
            self.s3_client.list_objects_v2(
                Bucket=bucket,
                Prefix=prefix,
                MaxKeys=1
            )
            
            # Test write permissions by attempting to check if we can put an object
            # We don't actually put anything, just check the permissions
            # This is done by trying to get the bucket location (requires ListBucket)
            self.s3_client.get_bucket_location(Bucket=bucket)
            
            return True
            
        except self.s3_client.exceptions.NoSuchBucket:
            self.console.print(f"[red]S3 bucket '{bucket}' does not exist[/red]")
            return False
        except self.s3_client.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'AccessDenied':
                self.console.print(f"[red]Access denied to S3 bucket '{bucket}'[/red]")
                self.console.print("[yellow]Check your AWS credentials and IAM permissions[/yellow]")
            elif error_code == 'Forbidden':
                self.console.print(f"[red]Forbidden access to S3 bucket '{bucket}'[/red]")
                self.console.print("[yellow]Your AWS profile may not have the required permissions[/yellow]")
            else:
                self.console.print(f"[red]S3 access error: {error_code} - {e}[/red]")
            return False
        except Exception as e:
            self.console.print(f"[red]Unexpected error validating S3 access: {e}[/red]")
            return False
