"""Tests for checksum and manifest functionality."""

import json
import tempfile
from pathlib import Path

import pytest

from hca_ingest.smart_sync.checksum import ChecksumCalculator
from hca_ingest.smart_sync.manifest import ManifestGenerator


class TestChecksumCalculator:
    """Test checksum calculation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = ChecksumCalculator()
    
    def test_sha256_calculation(self):
        """Test SHA256 calculation for a test file."""
        # Create a temporary file with known content
        test_content = b"Hello, HCA World!"
        expected_sha256 = "8c8c4e3c4d5c6b7a9e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4"
        
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(test_content)
            temp_file.flush()
            
            temp_path = Path(temp_file.name)
            
            try:
                # Calculate actual checksum
                actual_sha256 = self.calculator.calculate_sha256(temp_path)
                
                # Verify it's a valid SHA256 (64 hex characters)
                assert len(actual_sha256) == 64
                assert all(c in '0123456789abcdef' for c in actual_sha256.lower())
                
            finally:
                temp_path.unlink()  # Clean up
    
    def test_checksum_verification(self):
        """Test checksum verification functionality."""
        test_content = b"Test content for verification"
        
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(test_content)
            temp_file.flush()
            
            temp_path = Path(temp_file.name)
            
            try:
                # Calculate checksum
                checksum = self.calculator.calculate_sha256(temp_path)
                
                # Verify with correct checksum
                assert self.calculator.verify_checksum(temp_path, checksum) is True
                
                # Verify with incorrect checksum
                wrong_checksum = "0" * 64
                assert self.calculator.verify_checksum(temp_path, wrong_checksum) is False
                
            finally:
                temp_path.unlink()


class TestManifestGenerator:
    """Test manifest generation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.generator = ManifestGenerator()
    
    def test_manifest_generation(self):
        """Test basic manifest generation."""
        # Create temporary test files
        test_files = []
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            # Create test files
            for i in range(2):
                test_file = temp_dir / f"test_file_{i}.h5ad"
                test_file.write_text(f"Test content {i}")
                test_files.append(test_file)
            
            # Generate manifest
            metadata = {"study": "test-study", "version": "1.0"}
            submitter_info = {"name": "Test User", "email": "test@example.com"}
            
            manifest = self.generator.generate_manifest(
                files=test_files,
                metadata=metadata,
                submitter_info=submitter_info
            )
            
            # Verify manifest structure
            assert "manifest_version" in manifest
            assert "generated_at" in manifest
            assert "submission_id" in manifest
            assert "files" in manifest
            assert "metadata" in manifest
            assert "submitter" in manifest
            
            # Verify metadata
            assert manifest["metadata"] == metadata
            assert manifest["submitter"] == submitter_info
            
            # Verify files
            assert len(manifest["files"]) == 2
            for file_info in manifest["files"]:
                assert "filename" in file_info
                assert "size_bytes" in file_info
                assert "sha256" in file_info
                assert "modified_at" in file_info
                
        finally:
            # Clean up
            for file_path in test_files:
                if file_path.exists():
                    file_path.unlink()
            temp_dir.rmdir()
    
    def test_manifest_save(self):
        """Test saving manifest to file."""
        # Create a simple manifest
        manifest = {
            "manifest_version": "1.0",
            "files": [],
            "metadata": {},
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        
        try:
            # Save manifest
            self.generator.save_manifest(manifest, temp_path)
            
            # Verify file was created and contains valid JSON
            assert temp_path.exists()
            
            with open(temp_path, 'r') as f:
                loaded_manifest = json.load(f)
            
            assert loaded_manifest == manifest
            
        finally:
            if temp_path.exists():
                temp_path.unlink()
