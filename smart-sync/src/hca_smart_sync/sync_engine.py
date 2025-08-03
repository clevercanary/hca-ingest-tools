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

from hca_smart_sync.config import Config
from hca_smart_sync.checksum import ChecksumCalculator
from hca_smart_sync.manifest import ManifestGenerator


class SmartSync:
    """Smart synchronization engine for HCA data uploads."""
    
    def __init__(self, config: Config, console: Optional[Console] = None):
        """Initialize the sync engine."""
        self.config = config
        self.console = console or Console()
        self.checksum_calculator = ChecksumCalculator()
        self.manifest_generator = ManifestGenerator()
        
        # AWS clients will be created lazily to use current config
        self._s3_client = None
    
    @property
    def s3_client(self) -> boto3.client:
        """Get S3 client, creating it lazily with current config."""
        if self._s3_client is None:
            session = boto3.Session(profile_name=self.config.aws.profile)
            self._s3_client = session.client('s3', region_name=self.config.aws.region)
        return self._s3_client
    
    def _reset_aws_clients(self) -> None:
        """Reset AWS clients to pick up config changes."""
        self._s3_client = None
    
    def sync(
        self,
        local_path: Path,
        s3_path: str,
        dry_run: bool = False,
        verbose: bool = False,
        force: bool = False,
        plan_only: bool = False
    ) -> Dict:
        """
        Perform smart sync of .h5ad files to S3.
        
        Args:
            local_path: Local directory to scan
            s3_path: S3 destination path
            dry_run: Show what would be uploaded without uploading
            verbose: Enable verbose output
            force: Force upload even if files haven't changed
            plan_only: Only return the upload plan without executing the upload
            
        Returns:
            Dictionary with sync results
        """
        # Step 0: Validate S3 access before proceeding
        if not self._validate_s3_access(s3_path):
            return {"files_uploaded": 0, "manifest_path": None, "error": "access_denied"}
        
        # Scan for .h5ad files in current directory
        local_files = self._scan_local_files(local_path)
        
        # Compare with S3 to determine what needs uploading
        files_to_upload = self._compare_with_s3(local_files, s3_path, force)
        
        if not local_files:
            return {"files_uploaded": 0, "files_to_upload": [], "manifest_path": None, "no_files_found": True}
        
        if not files_to_upload:
            return {
                "files_uploaded": 0, 
                "files_to_upload": [], 
                "manifest_path": None,
                "local_files": local_files,  # Include local files so CLI can show count
                "all_up_to_date": True  # Flag to indicate files exist but are up-to-date
            }
        
        # Sort files alphabetically once for consistent ordering throughout workflow
        files_to_upload = sorted(files_to_upload, key=lambda x: x['filename'])
        
        # For dry run, return early with the plan
        if dry_run:
            return {
                "files_uploaded": 0,
                "files_to_upload": files_to_upload,
                "manifest_path": None,
                "dry_run": True
            }
        
        # For plan only, return early with the plan
        if plan_only:
            return {
                "files_uploaded": 0,
                "files_to_upload": files_to_upload,
                "manifest_path": None,
                "plan_only": True
            }
        
        # For force mode or when CLI has already confirmed, proceed with upload
        # Step 4.5: Generate and save manifest locally first (before uploads)
        manifest_path = None
        if not dry_run:
            manifest_path = self._generate_and_save_manifest_locally(files_to_upload, s3_path, local_path)
        
        # Step 5: Upload files using AWS CLI
        uploaded_files = []
        if not dry_run:
            uploaded_files = self._upload_files(files_to_upload, s3_path)
        else:
            uploaded_files = files_to_upload  # For dry run reporting
        
        # Step 6: Upload manifest to S3 (if we have uploaded files)
        if uploaded_files and not dry_run and manifest_path:
            self._upload_manifest_to_s3(manifest_path, s3_path)
        
        return {
            "files_uploaded": len(uploaded_files),
            "files_to_upload": files_to_upload,
            "manifest_path": manifest_path,
            "files": [f["local_path"].name for f in uploaded_files]
        }
    
    def _scan_local_files(self, local_path: Path) -> List[Dict]:
        """Scan for .h5ad files in the local directory."""
        local_files = []
        
        for file_path in local_path.glob("*.h5ad"):
            if file_path.is_file():
                # Calculate checksum
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
                    # Treat any access error as "new" to be safe
                    files_to_upload.append({**local_file, "reason": "new"})
        
        return files_to_upload
    
    def _upload_files(self, files_to_upload: List[Dict], s3_path: str) -> List[Dict]:
        """Upload files using AWS CLI."""
        uploaded_files = []
        bucket, prefix = self._parse_s3_path(s3_path)
        
        for file_info in files_to_upload:
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
                
                # Execute upload with output capture for better error handling
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                
                uploaded_files.append(file_info)
                
                # Show success message after each upload
                self.console.print(f"[green]Successfully uploaded: {file_info['filename']}[/green]")
                self.console.print()  # Add blank line between uploads
                
            except subprocess.CalledProcessError as e:
                # Enhance the error with detailed AWS CLI output, but preserve original exception type
                error_details = [f"Failed to upload {file_info['filename']}"]
                
                if e.stderr:
                    error_details.append(f"AWS CLI Error: {e.stderr.strip()}")
                if e.stdout:
                    error_details.append(f"AWS CLI Output: {e.stdout.strip()}")
                    
                error_details.extend([
                    f"Command: {' '.join(cmd)}",
                    f"Exit code: {e.returncode}"
                ])
                
                error_msg = "\n".join(error_details)
                self.console.print(f"[red]❌ {error_msg}[/red]")
                
                # Re-raise the original exception type with enhanced message
                raise subprocess.CalledProcessError(
                    e.returncode, 
                    e.cmd, 
                    output=e.stdout, 
                    stderr=error_msg  # Enhanced error message in stderr
                ) from e
        
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
    
    def _upload_manifest_to_s3(self, manifest_path: str, s3_path: str) -> None:
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
            
        except subprocess.CalledProcessError as e:
            # Provide detailed error information from AWS CLI
            error_msg = f"Failed to upload manifest"
            if e.stderr:
                error_msg += f"\nAWS CLI Error: {e.stderr.strip()}"
            if e.stdout:
                error_msg += f"\nAWS CLI Output: {e.stdout.strip()}"
            error_msg += f"\nCommand: {' '.join(cmd)}"
            error_msg += f"\nExit code: {e.returncode}"
            
            self.console.print(f"[red]❌ {error_msg}[/red]")
            raise RuntimeError(error_msg) from e
    
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
            return False
        except self.s3_client.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'AccessDenied':
                return False
            elif error_code == 'Forbidden':
                return False
            else:
                return False
        except Exception as e:
            return False
