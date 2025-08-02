"""Checksum calculation utilities for data integrity verification."""

import hashlib
from pathlib import Path
from typing import BinaryIO


class ChecksumCalculator:
    """Calculate checksums for files to ensure data integrity."""
    
    def __init__(self, chunk_size: int = 8192):
        """
        Initialize the checksum calculator.
        
        Args:
            chunk_size: Size of chunks to read when calculating checksums
        """
        self.chunk_size = chunk_size
    
    def calculate_sha256(self, file_path: Path) -> str:
        """
        Calculate SHA256 checksum for a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Hexadecimal SHA256 checksum string
        """
        sha256_hash = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            # Read file in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(self.chunk_size), b""):
                sha256_hash.update(chunk)
        
        return sha256_hash.hexdigest()
    
    def calculate_sha256_from_stream(self, stream: BinaryIO) -> str:
        """
        Calculate SHA256 checksum from a binary stream.
        
        Args:
            stream: Binary stream to read from
            
        Returns:
            Hexadecimal SHA256 checksum string
        """
        sha256_hash = hashlib.sha256()
        
        # Read stream in chunks
        for chunk in iter(lambda: stream.read(self.chunk_size), b""):
            sha256_hash.update(chunk)
        
        return sha256_hash.hexdigest()
    
    def verify_checksum(self, file_path: Path, expected_checksum: str) -> bool:
        """
        Verify that a file's checksum matches the expected value.
        
        Args:
            file_path: Path to the file to verify
            expected_checksum: Expected SHA256 checksum
            
        Returns:
            True if checksums match, False otherwise
        """
        actual_checksum = self.calculate_sha256(file_path)
        return actual_checksum.lower() == expected_checksum.lower()
