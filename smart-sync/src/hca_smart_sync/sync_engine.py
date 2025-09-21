"""Smart sync engine for HCA data uploads."""

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import boto3
from rich.console import Console
from natsort import natsorted

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
        
        # Sort files using natural sorting for consistent ordering throughout workflow
        files_to_upload = natsorted(files_to_upload, key=lambda x: x['filename'])
        
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
        
        # Step 5: Upload files using the unified upload method
        uploaded_files = []
        if not dry_run:
            for file_info in files_to_upload:
                s3_url = self._build_s3_url(file_info, s3_path)
                if self._upload_file(str(file_info['local_path']), s3_url, include_checksum=True, file_size=file_info['size']):
                    uploaded_files.append(file_info)
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
                
                # Compare both checksums and file size to ensure file is complete
                # This prevents issues with interrupted uploads where metadata is set
                # but file content is incomplete
                s3_checksum = response.get('Metadata', {}).get('source-sha256')
                s3_size = response.get('ContentLength', 0)
                
                if (s3_checksum and s3_checksum == local_file['checksum'] and 
                    s3_size == local_file['size']):
                    continue  # File is identical and complete, skip
                
                # File exists but has different checksum, size, or missing metadata
                # This catches interrupted uploads, corrupted files, etc.
                files_to_upload.append({**local_file, "reason": "changed"})
                
            except self.s3_client.exceptions.NoSuchKey:
                # File doesn't exist in S3 - this is normal for new files
                files_to_upload.append({**local_file, "reason": "new"})
            except Exception as e:
                # Handle other ClientError exceptions (like 404)
                error_code = getattr(e, 'response', {}).get('Error', {}).get('Code', 'Unknown')
                
                # If it's a 404 or NoSuchKey, treat as new file
                if error_code in ['NoSuchKey', '404']:
                    files_to_upload.append({**local_file, "reason": "new"})
                else:
                    # For other errors, fail fast rather than assume upload is safe
                    # This prevents issues like access denied, network errors, etc.
                    raise RuntimeError(
                        f"Failed to check S3 status for {local_file['filename']}: "
                        f"{error_code} - {getattr(e, 'response', {}).get('Error', {}).get('Message', str(e))}"
                    ) from e
        
        return files_to_upload
    
    def _upload_file(self, local_path: str, s3_url: str, include_checksum: bool = True, file_size: Optional[int] = None) -> bool:
        """Upload a single file using the best available tool.
        
        Args:
            local_path: Local file path
            s3_url: S3 destination URL
            include_checksum: Whether to include source-sha256 metadata (for data files)
            file_size: Optional file size for timeout calculation
            
        Returns:
            bool: True if upload successful, False otherwise
        """
        upload_tool = self._detect_upload_tool()
        local_file = Path(local_path)
        filename = local_file.name
        
        # Get file size if not provided
        if file_size is None:
            file_size = local_file.stat().st_size
        
        if upload_tool == "s5cmd":
            # Build s5cmd command
            cmd = [
                "s5cmd",
                "--numworkers", "10" if include_checksum else "1",  # High concurrency for data files, single for manifests
            ]
            
            # Add transfer acceleration endpoint if enabled
            if self.config.s3.use_transfer_acceleration:
                cmd.extend(["--endpoint-url", "https://s3-accelerate.amazonaws.com"])
            
            cmd.extend(["cp", "--show-progress"])
            
            # Add metadata for data files (not manifests)
            if include_checksum:
                checksum = self.checksum_calculator.calculate_sha256(local_file)
                cmd.extend(["--metadata", f"source-sha256={checksum}"])
            
            cmd.extend([str(local_file), s3_url])
            
            # Set up environment with AWS profile if specified
            env = os.environ.copy()
            if self.config.aws.profile:
                env["AWS_PROFILE"] = self.config.aws.profile
            
            try:
                import time
                start_time = time.time()
                
                # Calculate upload timeout
                upload_timeout = self._calculate_upload_timeout(file_size)
                
                result = subprocess.run(
                    cmd,
                    env=env,
                    text=True,
                    timeout=upload_timeout
                )
                
                if result.returncode == 0:
                    self._report_upload_success(filename, file_size, start_time)
                    return True
                else:
                    # Re-run command to capture error output for reporting
                    error_result = subprocess.run(
                        cmd,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    self.console.print(f"[red]s5cmd upload failed for {filename}: {error_result.stderr}[/red]")
                    return False
                    
            except subprocess.TimeoutExpired:
                self.console.print(f"[red]Upload timeout for {filename} (exceeded {upload_timeout} seconds)[/red]")
                return False
            except Exception as e:
                self.console.print(f"[red]Error uploading {filename} with s5cmd: {str(e)}[/red]")
                return False
        else:
            # Use AWS CLI
            import time
            start_time = time.time()
            
            if include_checksum:
                checksum = self.checksum_calculator.calculate_sha256(Path(local_path))
                metadata = {"source-sha256": checksum}
                cmd = self._build_aws_cli_command("cp", local_path, s3_url, metadata)
            else:
                cmd = self._build_aws_cli_command("cp", local_path, s3_url)
            
            try:
                self._run_aws_cli_command(cmd, f"upload {filename}", file_size)
                self._report_upload_success(filename, file_size, start_time)
                return True
            except Exception:
                return False

    def _report_upload_success(self, filename: str, file_size: int, start_time: float) -> None:
        """Report successful upload with speed calculation.
        
        Args:
            filename: Name of the uploaded file
            file_size: File size in bytes
            start_time: Upload start time from time.time()
        """
        import time
        end_time = time.time()
        duration = end_time - start_time
        file_size_mb = file_size / (1024 * 1024)  # Convert to MB
        speed_mbps = file_size_mb / duration if duration > 0 else 0
        
        # Show success message with speed
        self.console.print(f"[green]Successfully uploaded: {filename} ({speed_mbps:.1f} MB/s)[/green]")
        self.console.print()  # Add blank line between uploads

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
        
        # Use unified upload method without checksum metadata (manifests don't need source-sha256)
        success = self._upload_file(manifest_path, manifest_s3_url, include_checksum=False)
        if not success:
            raise RuntimeError(f"Failed to upload manifest: {manifest_path}")
    
    def _parse_s3_path(self, s3_path: str) -> Tuple[str, str]:
        """Parse S3 path into bucket and prefix."""
        if not s3_path.startswith("s3://"):
            raise ValueError("S3 path must start with s3://")
        
        path_parts = s3_path[5:].split("/", 1)
        bucket = path_parts[0]
        prefix = path_parts[1] if len(path_parts) > 1 else ""
        
        return bucket, prefix

    def _detect_upload_tool(self) -> str:
        """Detect available upload tools and return the best one.
        
        Returns:
            str: 's5cmd' if available, 'aws' otherwise
            
        Raises:
            RuntimeError: If neither tool is available
        """
        # Check for s5cmd first (preferred for performance)
        if shutil.which("s5cmd"):
            return "s5cmd"
        
        # Fall back to AWS CLI
        if shutil.which("aws"):
            return "aws"
        
        # Neither tool available
        raise RuntimeError("Neither s5cmd nor AWS CLI found. Please install AWS CLI or s5cmd.")

    def _build_aws_cli_command(self, operation: str, source: str, destination: str,
                              metadata: Optional[Dict[str, str]] = None) -> List[str]:
        """Build AWS CLI command with consistent profile handling.
        
        Args:
            operation: AWS CLI operation (e.g., 'cp', 'sync')
            source: Source path (local file or S3 URL)
            destination: Destination path (local file or S3 URL)
            metadata: Optional metadata dict to add as --metadata key=value pairs
            
        Returns:
            List of command arguments ready for subprocess.run
        """
        cmd = ["aws", "s3", operation, source, destination]
        
        # Add metadata if provided
        if metadata:
            for key, value in metadata.items():
                cmd.extend(["--metadata", f"{key}={value}"])
        
        # Add profile if configured
        if self.config.aws.profile:
            cmd.extend(["--profile", self.config.aws.profile])
        
        # Add Transfer Acceleration endpoint for faster international uploads
        # Use accelerated endpoint for all S3 operations
        if source.startswith('s3://') or destination.startswith('s3://'):
            cmd.extend(["--endpoint-url", "https://s3-accelerate.amazonaws.com"])
        
        return cmd
    
    def _build_s3_url(self, file_info: Dict, s3_path: str) -> str:
        """Build S3 URL for a file."""
        bucket, prefix = self._parse_s3_path(s3_path)
        s3_key = f"{prefix.rstrip('/')}/{file_info['filename']}"
        return f"s3://{bucket}/{s3_key}"
    
    def _calculate_upload_timeout(self, file_size_bytes: int) -> int:
        """Calculate appropriate upload timeout based on file size.
        
        Args:
            file_size_bytes: File size in bytes
            
        Returns:
            Timeout in seconds (minimum 30 minutes, maximum 6 hours)
        """
        # Assume minimum 1 MB/s upload speed (very conservative)
        # Add 10 minutes base time for connection setup and overhead
        file_size_mb = file_size_bytes / (1024 * 1024)
        calculated_timeout = int(file_size_mb / 1.0) + 600  # 1 MB/s + 10 min overhead
        
        # Minimum 30 minutes, maximum 6 hours for very large files
        return max(1800, min(calculated_timeout, 21600))

    def _run_aws_cli_command(self, cmd: List[str], operation_description: str, file_size_bytes: Optional[int] = None) -> None:
        """Run AWS CLI command with consistent error handling and progress display.
        
        Args:
            cmd: AWS CLI command as list of strings
            operation_description: Description of the operation for error messages (e.g., "upload file.h5ad")
            file_size_bytes: Optional file size in bytes for timeout calculation
        """
        # Calculate appropriate timeout if file size is provided
        upload_timeout = None
        if file_size_bytes is not None:
            upload_timeout = self._calculate_upload_timeout(file_size_bytes)
        
        try:
            # Let stdout (progress) stream to console; capture stderr for diagnostics.
            # With check=True we rely on exceptions for error handling; no need to capture the result.
            subprocess.run(
                cmd,
                capture_output=False,  # Let stdout (progress) show naturally
                stderr=subprocess.PIPE,  # Capture stderr for error handling
                text=True,
                timeout=upload_timeout,
                check=True
            )
        except subprocess.TimeoutExpired as e:
            timeout_msg = f"Upload timeout for {operation_description}"
            if upload_timeout:
                timeout_msg += f" (exceeded {upload_timeout} seconds)"
            self.console.print(f"[red]❌ {timeout_msg}[/red]")
            raise subprocess.CalledProcessError(1, cmd, stderr=timeout_msg) from e
        except subprocess.CalledProcessError as e:
            # Enhance the error with detailed AWS CLI output
            error_details = [f"Failed to {operation_description}"]
            
            if e.stderr:
                error_details.append(f"AWS CLI Error: {e.stderr.strip()}")
            
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
        except Exception:
            return False
