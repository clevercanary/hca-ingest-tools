"""Tests for sync engine functionality."""

import tempfile
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from hca_smart_sync.config import Config, AWSConfig, S3Config, ManifestConfig
from hca_smart_sync.sync_engine import SmartSync


class TestSmartSync:
    """Test SmartSync engine functionality."""
    
    def setup_method(self):
        """Set up test configuration."""
        self.config = Config(
            aws=AWSConfig(
                profile="test-profile",
                region="us-east-1"
            ),
            s3=S3Config(
                bucket="test-bucket",
                prefix="test-atlas/source-datasets"
            ),
            manifest=ManifestConfig(
                filename_template="manifest-{timestamp}.json"
            )
        )
    
    def test_init(self):
        """Test SmartSync initialization."""
        sync = SmartSync(self.config)
        
        assert sync.config == self.config
        assert sync._s3_client is None  # Lazy initialization
        assert sync.checksum_calculator is not None
        assert sync.manifest_generator is not None
    
    def test_scan_local_files_empty_directory(self):
        """Test scanning an empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            sync = SmartSync(self.config)
            files = sync._scan_local_files(Path(temp_dir))
            
            assert files == []
    
    def test_scan_local_files_with_h5ad_files(self):
        """Test scanning directory with .h5ad files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test .h5ad files
            (temp_path / "file1.h5ad").write_text("test data 1")
            (temp_path / "file2.h5ad").write_text("test data 2")
            (temp_path / "other.txt").write_text("not h5ad")
            
            sync = SmartSync(self.config)
            files = sync._scan_local_files(temp_path)
            
            # Should only find .h5ad files
            assert len(files) == 2
            file_names = [f['filename'] for f in files]
            assert "file1.h5ad" in file_names
            assert "file2.h5ad" in file_names
            assert "other.txt" not in file_names
            
            # Check that each file has the expected structure
            for file_info in files:
                assert 'local_path' in file_info
                assert 'filename' in file_info
                assert 'size' in file_info
                assert 'checksum' in file_info
                assert 'modified' in file_info
    
    def test_parse_s3_path(self):
        """Test S3 path parsing."""
        sync = SmartSync(self.config)
        
        bucket, key = sync._parse_s3_path("s3://test-bucket/path/to/folder")
        assert bucket == "test-bucket"
        assert key == "path/to/folder"
        
        bucket, key = sync._parse_s3_path("s3://my-bucket/")
        assert bucket == "my-bucket"
        assert key == ""
    
    @patch('boto3.Session')
    def test_s3_client_lazy_initialization(self, mock_session):
        """Test that S3 client is created lazily."""
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        
        sync = SmartSync(self.config)
        
        # First access should create the client
        client1 = sync.s3_client
        assert client1 == mock_client
        mock_session.assert_called_once_with(profile_name="test-profile")
        
        # Second access should return the same client
        client2 = sync.s3_client
        assert client2 == mock_client
        assert client1 is client2
        
        # Session should only be called once (cached)
        mock_session.assert_called_once()
    
    def test_reset_aws_clients(self):
        """Test resetting AWS clients."""
        sync = SmartSync(self.config)
        
        # Set a mock client
        sync._s3_client = Mock()
        assert sync._s3_client is not None
        
        # Reset should clear the client
        sync._reset_aws_clients()
        assert sync._s3_client is None

    @patch('boto3.Session')
    def test_compare_with_s3_missing_files(self, mock_session):
        """Test S3 comparison when files don't exist in S3 (404/NoSuchKey)."""
        # Mock S3 client that raises NoSuchKey for head_object calls
        mock_s3_client = Mock()
        mock_session.return_value.client.return_value = mock_s3_client
        
        # Configure head_object to raise NoSuchKey exception
        from botocore.exceptions import ClientError
        mock_s3_client.exceptions.NoSuchKey = ClientError
        mock_s3_client.head_object.side_effect = ClientError(
            error_response={'Error': {'Code': 'NoSuchKey', 'Message': 'Not Found'}},
            operation_name='HeadObject'
        )
        
        sync = SmartSync(self.config)
        
        # Create mock local files
        local_files = [
            {
                'filename': 'test1.h5ad',
                'local_path': Path('/tmp/test1.h5ad'),
                'size': 1024,
                'checksum': 'abc123',
                'modified': '2023-01-01T00:00:00Z'
            },
            {
                'filename': 'test2.h5ad', 
                'local_path': Path('/tmp/test2.h5ad'),
                'size': 2048,
                'checksum': 'def456',
                'modified': '2023-01-01T00:00:00Z'
            }
        ]
        
        # Test comparison with missing S3 files
        files_to_upload = sync._compare_with_s3(local_files, "s3://test-bucket/path/", force=False)
        
        # All files should be marked for upload as "new"
        assert len(files_to_upload) == 2
        assert files_to_upload[0]['filename'] == 'test1.h5ad'
        assert files_to_upload[0]['reason'] == 'new'
        assert files_to_upload[1]['filename'] == 'test2.h5ad'
        assert files_to_upload[1]['reason'] == 'new'
        
        # Verify head_object was called for each file
        assert mock_s3_client.head_object.call_count == 2

    @patch('boto3.Session')
    def test_compare_with_s3_404_client_error(self, mock_session):
        """Test S3 comparison when files return 404 ClientError."""
        # Mock S3 client that raises 404 ClientError for head_object calls
        mock_s3_client = Mock()
        mock_session.return_value.client.return_value = mock_s3_client
        
        # Configure head_object to raise 404 ClientError (different from NoSuchKey)
        from botocore.exceptions import ClientError
        mock_s3_client.exceptions.NoSuchKey = ClientError
        mock_s3_client.head_object.side_effect = ClientError(
            error_response={'Error': {'Code': '404', 'Message': 'Not Found'}},
            operation_name='HeadObject'
        )
        
        sync = SmartSync(self.config)
        
        # Create mock local file
        local_files = [
            {
                'filename': 'missing.h5ad',
                'local_path': Path('/tmp/missing.h5ad'),
                'size': 1024,
                'checksum': 'xyz789',
                'modified': '2023-01-01T00:00:00Z'
            }
        ]
        
        # Test comparison with 404 error
        files_to_upload = sync._compare_with_s3(local_files, "s3://test-bucket/path/", force=False)
        
        # File should be marked for upload as "new" (404 should be treated as missing)
        assert len(files_to_upload) == 1
        assert files_to_upload[0]['filename'] == 'missing.h5ad'
        assert files_to_upload[0]['reason'] == 'new'
        
        # Verify head_object was called
        mock_s3_client.head_object.assert_called_once()


    @patch('boto3.Session')
    def test_compare_with_s3_interrupted_upload_detection(self, mock_session):
        """Test that interrupted uploads are detected and marked for re-upload."""
        # Mock S3 client to simulate an interrupted upload scenario
        mock_s3_client = Mock()
        mock_session.return_value.client.return_value = mock_s3_client
        
        # Simulate S3 object with correct metadata but wrong size (interrupted upload)
        mock_response = {
            'ContentLength': 512,  # S3 shows smaller size (interrupted)
            'Metadata': {
                'source-sha256': 'abc123'  # Metadata was set before interruption
            }
        }
        mock_s3_client.head_object.return_value = mock_response
        
        local_files = [
            {
                'filename': 'interrupted.h5ad',
                'local_path': Path('/tmp/interrupted.h5ad'),
                'size': 1024,  # Local file is larger than S3 object
                'checksum': 'abc123',  # Same checksum as S3 metadata
                'modified': '2023-01-01T00:00:00Z'
            }
        ]
        
        # Create sync engine with mocked S3 client
        sync = SmartSync(self.config)
        
        # Test comparison - should detect size mismatch and mark for upload
        files_to_upload = sync._compare_with_s3(local_files, "s3://test-bucket/path/", force=False)
        
        # File should be marked for upload due to size mismatch
        assert len(files_to_upload) == 1
        assert files_to_upload[0]['filename'] == 'interrupted.h5ad'
        assert files_to_upload[0]['reason'] == 'changed'
        
        # Verify head_object was called
        assert mock_s3_client.head_object.call_count == 1

    @patch('boto3.Session')
    def test_compare_with_s3_complete_upload_detection(self, mock_session):
        """Test that complete uploads with matching size and checksum are skipped."""
        # Mock S3 client to simulate a complete, valid upload
        mock_s3_client = Mock()
        mock_session.return_value.client.return_value = mock_s3_client
        
        # Simulate S3 object with correct metadata AND correct size
        mock_response = {
            'ContentLength': 1024,  # Matches local file size
            'Metadata': {
                'source-sha256': 'abc123'  # Matches local file checksum
            }
        }
        mock_s3_client.head_object.return_value = mock_response
        
        local_files = [
            {
                'filename': 'complete.h5ad',
                'local_path': Path('/tmp/complete.h5ad'),
                'size': 1024,  # Same size as S3 object
                'checksum': 'abc123',  # Same checksum as S3 metadata
                'modified': '2023-01-01T00:00:00Z'
            }
        ]
        
        # Create sync engine with mocked S3 client
        sync = SmartSync(self.config)
        
        # Test comparison - should skip file as it's complete and identical
        files_to_upload = sync._compare_with_s3(local_files, "s3://test-bucket/path/", force=False)
        
        # No files should be marked for upload
        assert len(files_to_upload) == 0
        
        # Verify head_object was called
        assert mock_s3_client.head_object.call_count == 1

    @patch('boto3.Session')
    def test_compare_with_s3_missing_metadata_detection(self, mock_session):
        """Test that files with missing source-sha256 metadata are marked for re-upload."""
        # Mock S3 client to simulate an object without our metadata
        mock_s3_client = Mock()
        mock_session.return_value.client.return_value = mock_s3_client
        
        # Simulate S3 object with correct size but missing metadata
        mock_response = {
            'ContentLength': 1024,  # Correct size
            'Metadata': {}  # No source-sha256 metadata
        }
        mock_s3_client.head_object.return_value = mock_response
        
        local_files = [
            {
                'filename': 'no_metadata.h5ad',
                'local_path': Path('/tmp/no_metadata.h5ad'),
                'size': 1024,
                'checksum': 'abc123',
                'modified': '2023-01-01T00:00:00Z'
            }
        ]
        
        # Create sync engine with mocked S3 client
        sync = SmartSync(self.config)
        
        # Test comparison - should mark for upload due to missing metadata
        files_to_upload = sync._compare_with_s3(local_files, "s3://test-bucket/path/", force=False)
        
        # File should be marked for upload due to missing metadata
        assert len(files_to_upload) == 1
        assert files_to_upload[0]['filename'] == 'no_metadata.h5ad'
        assert files_to_upload[0]['reason'] == 'changed'
        
        # Verify head_object was called
        assert mock_s3_client.head_object.call_count == 1

class TestSubprocessErrorHandling:
    """Test enhanced subprocess error handling in sync engine."""
    
    def setup_method(self):
        """Set up test configuration."""
        self.config = Config(
            aws=AWSConfig(
                profile="test-profile",
                region="us-east-1"
            ),
            s3=S3Config(
                bucket="test-bucket",
                prefix="test-atlas/source-datasets"
            ),
            manifest=ManifestConfig(
                filename_template="manifest-{timestamp}.json"
            )
        )
    
    @patch('subprocess.run')
    def test_run_aws_cli_command_error_with_stderr(self, mock_run):
        """Test that AWS CLI command errors with stderr are properly captured and re-raised."""
        # Mock a CalledProcessError with stderr output
        error = subprocess.CalledProcessError(
            returncode=1,
            cmd=['aws', 's3', 'cp', 'test.h5ad', 's3://bucket/path/'],
            output="some stdout",
            stderr="AccessDenied: Access denied to S3 bucket"
        )
        mock_run.side_effect = error
        
        # Create mock console to capture output
        mock_console = Mock()
        sync = SmartSync(self.config, console=mock_console)
        
        cmd = ['aws', 's3', 'cp', 'test.h5ad', 's3://bucket/path/']
        
        # Should re-raise CalledProcessError (not RuntimeError)
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            sync._run_aws_cli_command(cmd, "upload test.h5ad")
        
        # Verify the re-raised exception has enhanced error message
        raised_exception = exc_info.value
        assert raised_exception.returncode == 1
        assert "Failed to upload test.h5ad" in raised_exception.stderr
        assert "AWS CLI Error: AccessDenied: Access denied to S3 bucket" in raised_exception.stderr
        assert "Exit code: 1" in raised_exception.stderr
        
        # Verify console output was called with error message
        mock_console.print.assert_called()
        console_call_args = mock_console.print.call_args[0][0]
        assert "[red]❌" in console_call_args
        assert "Failed to upload test.h5ad" in console_call_args
    
    @patch('subprocess.run')
    def test_run_aws_cli_command_success_with_stderr_capture(self, mock_run):
        """Test that successful AWS CLI commands work with stderr capture only."""
        # Mock successful subprocess run
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        mock_console = Mock()
        sync = SmartSync(self.config, console=mock_console)
        
        cmd = ['aws', 's3', 'cp', 'test.h5ad', 's3://bucket/path/']
        
        # Should complete successfully
        sync._run_aws_cli_command(cmd, "upload test.h5ad")
        
        # Verify subprocess.run was called with stderr=PIPE only
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[1]['stderr'] == subprocess.PIPE
        assert call_args[1]['text'] is True
        assert call_args[1]['check'] is True
        # stdout should NOT be captured (not in call_args)
        assert 'stdout' not in call_args[1] or call_args[1].get('stdout') is None
    
    @patch('subprocess.run')
    def test_upload_files_uses_reusable_method(self, mock_run):
        """Test that _upload_files uses the new reusable _run_aws_cli_command method."""
        # Mock successful subprocess run
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        mock_console = Mock()
        sync = SmartSync(self.config, console=mock_console)
        
        files_to_upload = [
            {
                'filename': 'test.h5ad',
                'local_path': '/path/test.h5ad',
                'checksum': 'abc123'
            }
        ]
        
        # Should complete successfully
        result = sync._upload_files(files_to_upload, "s3://test-bucket/test-atlas/source-datasets/")
        
        # Verify subprocess.run was called once (by the reusable method)
        mock_run.assert_called_once()
        
        # Verify success message was printed
        success_calls = [call for call in mock_console.print.call_args_list 
                        if 'Successfully uploaded' in str(call)]
        assert len(success_calls) > 0
        
        # Verify file was added to uploaded_files
        assert len(result) == 1
        assert result[0]['filename'] == 'test.h5ad'
    
    @patch('subprocess.run')
    def test_manifest_upload_uses_reusable_method(self, mock_run):
        """Test that manifest upload uses the new reusable _run_aws_cli_command method."""
        # Mock successful subprocess run
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        mock_console = Mock()
        sync = SmartSync(self.config, console=mock_console)
        
        # Test the manifest upload method
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"test": "manifest"}')
            manifest_path = f.name
        
        try:
            sync._upload_manifest_to_s3(
                manifest_path, 
                "s3://test-bucket/test-atlas/source-datasets/"
            )
            
            # Verify subprocess.run was called once (by the reusable method)
            mock_run.assert_called_once()
            
            # Verify the command includes the manifest path and manifests folder
            call_args = mock_run.call_args[0][0]  # First positional arg (cmd)
            assert 'aws' in call_args
            assert 's3' in call_args
            assert 'cp' in call_args
            assert manifest_path in call_args
            assert 'manifests' in ' '.join(call_args)
            
        finally:
            # Clean up temp file
            Path(manifest_path).unlink(missing_ok=True)


class TestTransferAcceleration:
    """Test Transfer Acceleration command generation."""
    
    def setup_method(self):
        """Set up test configuration."""
        self.config = Config(
            aws=AWSConfig(
                profile="test-profile",
                region="us-east-1"
            ),
            s3=S3Config(
                bucket="test-bucket",
                prefix="test-atlas/source-datasets"
            ),
            manifest=ManifestConfig(
                filename_template="manifest-{timestamp}.json"
            )
        )
    
    def test_build_aws_cli_command_upload_with_transfer_acceleration(self):
        """Test that S3 upload commands include Transfer Acceleration endpoint."""
        sync = SmartSync(self.config)
        
        # Test local file to S3 upload
        cmd = sync._build_aws_cli_command(
            operation="cp",
            source="/local/path/test.h5ad",
            destination="s3://test-bucket/test-atlas/source-datasets/test.h5ad",
            metadata={"source-sha256": "abc123def456"}
        )
        
        # Verify Transfer Acceleration endpoint is included
        assert "--endpoint-url" in cmd
        endpoint_index = cmd.index("--endpoint-url")
        assert cmd[endpoint_index + 1] == "https://s3-accelerate.amazonaws.com"
        
        # Verify other expected components
        assert "aws" in cmd
        assert "s3" in cmd
        assert "cp" in cmd
        assert "/local/path/test.h5ad" in cmd
        assert "s3://test-bucket/test-atlas/source-datasets/test.h5ad" in cmd
        assert "--metadata" in cmd
        assert "source-sha256=abc123def456" in cmd
        assert "--profile" in cmd
        assert "test-profile" in cmd
    
    def test_build_aws_cli_command_download_with_transfer_acceleration(self):
        """Test that S3 download commands include Transfer Acceleration endpoint."""
        sync = SmartSync(self.config)
        
        # Test S3 to local file download
        cmd = sync._build_aws_cli_command(
            operation="cp",
            source="s3://test-bucket/test-atlas/source-datasets/test.h5ad",
            destination="/local/path/test.h5ad"
        )
        
        # Verify Transfer Acceleration endpoint is included
        assert "--endpoint-url" in cmd
        endpoint_index = cmd.index("--endpoint-url")
        assert cmd[endpoint_index + 1] == "https://s3-accelerate.amazonaws.com"
        
        # Verify other expected components
        assert "aws" in cmd
        assert "s3" in cmd
        assert "cp" in cmd
        assert "s3://test-bucket/test-atlas/source-datasets/test.h5ad" in cmd
        assert "/local/path/test.h5ad" in cmd
        assert "--profile" in cmd
        assert "test-profile" in cmd
    
    def test_build_aws_cli_command_s3_to_s3_with_transfer_acceleration(self):
        """Test that S3 to S3 copy commands include Transfer Acceleration endpoint."""
        sync = SmartSync(self.config)
        
        # Test S3 to S3 copy
        cmd = sync._build_aws_cli_command(
            operation="cp",
            source="s3://source-bucket/path/test.h5ad",
            destination="s3://dest-bucket/path/test.h5ad"
        )
        
        # Verify Transfer Acceleration endpoint is included
        assert "--endpoint-url" in cmd
        endpoint_index = cmd.index("--endpoint-url")
        assert cmd[endpoint_index + 1] == "https://s3-accelerate.amazonaws.com"
        
        # Verify other expected components
        assert "aws" in cmd
        assert "s3" in cmd
        assert "cp" in cmd
        assert "s3://source-bucket/path/test.h5ad" in cmd
        assert "s3://dest-bucket/path/test.h5ad" in cmd
        assert "--profile" in cmd
        assert "test-profile" in cmd
    
    def test_build_aws_cli_command_with_metadata_and_acceleration(self):
        """Test that metadata and Transfer Acceleration work together correctly."""
        sync = SmartSync(self.config)
        
        # Test with multiple metadata fields
        cmd = sync._build_aws_cli_command(
            operation="cp",
            source="/local/path/test.h5ad",
            destination="s3://test-bucket/test-atlas/source-datasets/test.h5ad",
            metadata={
                "source-sha256": "abc123def456",
                "upload-tool": "hca-smart-sync",
                "version": "1.0.0"
            }
        )
        
        # Verify Transfer Acceleration endpoint is included
        assert "--endpoint-url" in cmd
        endpoint_index = cmd.index("--endpoint-url")
        assert cmd[endpoint_index + 1] == "https://s3-accelerate.amazonaws.com"
        
        # Verify metadata is properly formatted (each field gets its own --metadata flag)
        assert "--metadata" in cmd
        
        # Count metadata occurrences (should be 3)
        metadata_count = cmd.count("--metadata")
        assert metadata_count == 3
        
        # Check that all metadata fields are present as separate arguments
        cmd_str = " ".join(cmd)
        assert "source-sha256=abc123def456" in cmd_str
        assert "upload-tool=hca-smart-sync" in cmd_str
        assert "version=1.0.0" in cmd_str
        
        # Verify command structure
        assert "aws" in cmd
        assert "s3" in cmd
        assert "cp" in cmd
        assert "--profile" in cmd
        assert "test-profile" in cmd
    
    def test_build_aws_cli_command_order_consistency(self):
        """Test that command arguments are in consistent order."""
        sync = SmartSync(self.config)
        
        cmd = sync._build_aws_cli_command(
            operation="cp",
            source="/local/path/test.h5ad",
            destination="s3://test-bucket/test-atlas/source-datasets/test.h5ad",
            metadata={"source-sha256": "abc123"}
        )
        
        # Verify basic command structure order
        assert cmd[0] == "aws"
        assert cmd[1] == "s3"
        assert cmd[2] == "cp"
        assert cmd[3] == "/local/path/test.h5ad"
        assert cmd[4] == "s3://test-bucket/test-atlas/source-datasets/test.h5ad"
        
        # Verify that profile and endpoint-url are present (order may vary for flags)
        assert "--profile" in cmd
        assert "--endpoint-url" in cmd
        assert "--metadata" in cmd
        
        # Verify endpoint URL value immediately follows the flag
        endpoint_index = cmd.index("--endpoint-url")
        assert cmd[endpoint_index + 1] == "https://s3-accelerate.amazonaws.com"
