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
    def test_upload_files_subprocess_error_with_stderr(self, mock_run):
        """Test that subprocess errors with stderr are properly captured and re-raised."""
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
        
        files_to_upload = [
            {
                'filename': 'test.h5ad',
                'local_path': '/path/test.h5ad',
                'checksum': 'abc123'
            }
        ]
        
        # Should re-raise CalledProcessError (not RuntimeError)
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            sync._upload_files(files_to_upload, "s3://test-bucket/test-atlas/source-datasets/")
        
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
    def test_upload_files_subprocess_error_with_stdout_and_stderr(self, mock_run):
        """Test subprocess error handling with both stdout and stderr."""
        error = subprocess.CalledProcessError(
            returncode=2,
            cmd=['aws', 's3', 'cp', 'data.h5ad', 's3://bucket/path/'],
            output="upload progress info",
            stderr="InvalidArgument: Invalid metadata format"
        )
        mock_run.side_effect = error
        
        mock_console = Mock()
        sync = SmartSync(self.config, console=mock_console)
        
        files_to_upload = [
            {
                'filename': 'data.h5ad',
                'local_path': '/path/data.h5ad',
                'checksum': 'def456'
            }
        ]
        
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            sync._upload_files(files_to_upload, "s3://test-bucket/test-atlas/source-datasets/")
        
        # Verify enhanced error message includes both stdout and stderr
        raised_exception = exc_info.value
        assert "AWS CLI Output: upload progress info" in raised_exception.stderr
        assert "AWS CLI Error: InvalidArgument: Invalid metadata format" in raised_exception.stderr
        assert "Exit code: 2" in raised_exception.stderr
    
    @patch('subprocess.run')
    def test_upload_files_success_with_capture_output(self, mock_run):
        """Test that successful uploads work with capture_output=True."""
        # Mock successful subprocess run
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "upload: test.h5ad to s3://bucket/path/test.h5ad"
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
        
        # Verify subprocess.run was called with capture_output=True
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[1]['capture_output'] is True
        assert call_args[1]['text'] is True
        assert call_args[1]['check'] is True
        
        # Verify success message was printed
        success_calls = [call for call in mock_console.print.call_args_list 
                        if 'Successfully uploaded' in str(call)]
        assert len(success_calls) > 0
        
        # Verify file was added to uploaded_files
        assert len(result) == 1
        assert result[0]['filename'] == 'test.h5ad'
