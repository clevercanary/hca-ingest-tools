"""Tests for checksum and manifest functionality."""

import json
import tempfile
from pathlib import Path
import hashlib
import pytest

from hca_smart_sync.checksum import ChecksumCalculator
from hca_smart_sync.manifest import ManifestGenerator
from hca_smart_sync.config import Config


class TestChecksumCalculator:
    """Test checksum calculation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = ChecksumCalculator()
    
    def test_sha256_known_answer(self):
        """Test SHA256 calculation against known answer from fixture file."""
        # Create fixture file with known content
        fixture_content = b"Hello, HCA World! This is a test file for checksum validation."
        # This SHA256 was calculated with our helper script and verified
        expected_sha256 = "5829c2cba87286e32a50f6a136c00eec2970c4b881f52875809622edc6a221a5"
        
        # Create fixture directory if it doesn't exist
        fixture_dir = Path(__file__).parent / "fixtures"
        fixture_dir.mkdir(exist_ok=True)
        
        fixture_path = fixture_dir / "small.txt"
        
        # Write fixture file
        with open(fixture_path, 'wb') as f:
            f.write(fixture_content)
        
        try:
            # Calculate checksum using our implementation
            actual_sha256 = self.calculator.calculate_sha256(fixture_path)
            
            # Verify against known answer
            assert actual_sha256 == expected_sha256, f"Expected {expected_sha256}, got {actual_sha256}"
            
            # Verify it's a valid SHA256 format
            assert len(actual_sha256) == 64
            assert all(c in '0123456789abcdef' for c in actual_sha256.lower())
            
        finally:
            # Clean up fixture file
            if fixture_path.exists():
                fixture_path.unlink()

    def test_sha256_large_file_multi_chunk(self):
        """Test SHA256 calculation for file larger than chunk size (8192 bytes)."""
        # Create content larger than default chunk size (8192 bytes)
        # Use deterministic content so we can verify the hash
        chunk_size = 8192
        large_content = b"A" * (chunk_size * 2 + 100)  # 16484 bytes (2+ chunks)
        
        # Calculate expected hash using Python's hashlib directly
        expected_sha256 = hashlib.sha256(large_content).hexdigest()
        
        # Create fixture directory if it doesn't exist
        fixture_dir = Path(__file__).parent / "fixtures"
        fixture_dir.mkdir(exist_ok=True)
        
        fixture_path = fixture_dir / "large.txt"
        
        # Write large fixture file
        with open(fixture_path, 'wb') as f:
            f.write(large_content)
        
        try:
            # Calculate checksum using our chunked implementation
            actual_sha256 = self.calculator.calculate_sha256(fixture_path)
            
            # Verify our chunked reading produces same result as direct calculation
            assert actual_sha256 == expected_sha256, f"Expected {expected_sha256}, got {actual_sha256}"
            
            # Verify it's a valid SHA256 format
            assert len(actual_sha256) == 64
            assert all(c in '0123456789abcdef' for c in actual_sha256.lower())
            
        finally:
            # Clean up fixture file
            if fixture_path.exists():
                fixture_path.unlink()

    def test_sha256_chunk_boundaries(self):
        """Test SHA256 calculation for files at chunk boundaries (edge cases)."""
        chunk_size = 8192  # Default chunk size from ChecksumCalculator
        
        # Test cases: exactly chunk size, chunk + 1, chunk - 1
        test_cases = [
            ("exactly_chunk", chunk_size),      # 8192 bytes - exactly one chunk
            ("chunk_plus_one", chunk_size + 1), # 8193 bytes - chunk + 1 byte
            ("chunk_minus_one", chunk_size - 1), # 8191 bytes - chunk - 1 byte
        ]
        
        fixture_dir = Path(__file__).parent / "fixtures"
        fixture_dir.mkdir(exist_ok=True)
        
        for test_name, file_size in test_cases:
            # Create deterministic content of exact size
            boundary_content = b"B" * file_size
            
            # Calculate expected hash using Python's hashlib directly
            expected_sha256 = hashlib.sha256(boundary_content).hexdigest()
            
            fixture_path = fixture_dir / f"{test_name}.txt"
            
            # Write boundary test file
            with open(fixture_path, 'wb') as f:
                f.write(boundary_content)
            
            try:
                # Calculate checksum using our chunked implementation
                actual_sha256 = self.calculator.calculate_sha256(fixture_path)
                
                # Verify our chunked reading produces same result as direct calculation
                assert actual_sha256 == expected_sha256, f"{test_name}: Expected {expected_sha256}, got {actual_sha256}"
                
                # Verify it's a valid SHA256 format
                assert len(actual_sha256) == 64
                assert all(c in '0123456789abcdef' for c in actual_sha256.lower())
                
            finally:
                # Clean up fixture file
                if fixture_path.exists():
                    fixture_path.unlink()

    def test_sha256_cross_validation_with_shasum(self):
        """Test SHA256 calculation against external shasum command-line tool."""
        import subprocess
        import shutil
        
        # Check if shasum is available (should be on macOS/Linux)
        if not shutil.which('shasum'):
            pytest.skip("shasum command not available on this system")
        
        # Create test content for cross-validation
        cross_val_content = b"Cross-validation test content for biological data integrity verification."
        
        fixture_dir = Path(__file__).parent / "fixtures"
        fixture_dir.mkdir(exist_ok=True)
        
        fixture_path = fixture_dir / "cross_validation.txt"
        
        # Write test file
        with open(fixture_path, 'wb') as f:
            f.write(cross_val_content)
        
        try:
            # Calculate checksum using our implementation
            our_sha256 = self.calculator.calculate_sha256(fixture_path)
            
            # Calculate checksum using external shasum tool
            result = subprocess.run(
                ['shasum', '-a', '256', str(fixture_path)],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse shasum output (format: "hash  filename")
            shasum_output = result.stdout.strip()
            external_sha256 = shasum_output.split()[0]
            
            # Verify our implementation matches external tool
            assert our_sha256 == external_sha256, f"Our implementation: {our_sha256}, shasum: {external_sha256}"
            
            # Verify it's a valid SHA256 format
            assert len(our_sha256) == 64
            assert all(c in '0123456789abcdef' for c in our_sha256.lower())
            
        except subprocess.CalledProcessError as e:
            pytest.fail(f"shasum command failed: {e}")
        finally:
            # Clean up fixture file
            if fixture_path.exists():
                fixture_path.unlink()

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
                if temp_path.exists():
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
    
    def test_manifest_natural_sorting_order(self):
        """Test that manifest generation uses natural sorting for file order."""
        # Create temporary test files with names that sort differently with natural vs lexicographic sorting
        test_files = []
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            # Create test files in a specific order that would be different with lexicographic sorting
            filenames = ['file10.h5ad', 'file2.h5ad', 'file1.h5ad']  # Intentionally out of natural order
            for filename in filenames:
                test_file = temp_dir / filename
                test_file.write_text(f"Test content for {filename}")
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
            assert "files" in manifest
            assert len(manifest["files"]) == 3
            
            # Verify natural sorting order in manifest: file1.h5ad, file2.h5ad, file10.h5ad
            # (NOT lexicographic order which would be: file1.h5ad, file10.h5ad, file2.h5ad)
            filenames_in_manifest = [file_info["filename"] for file_info in manifest["files"]]
            expected_natural_order = ['file1.h5ad', 'file2.h5ad', 'file10.h5ad']
            
            assert filenames_in_manifest == expected_natural_order, (
                f"Expected natural sort order {expected_natural_order}, "
                f"but got {filenames_in_manifest}"
            )
            
        finally:
            # Clean up
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
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
