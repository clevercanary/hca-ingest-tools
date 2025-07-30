"""Tests for sync engine functionality."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from hca_ingest.config import Config, AWSConfig, S3Config, ManifestConfig
from hca_ingest.smart_sync.sync_engine import SmartSync


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
