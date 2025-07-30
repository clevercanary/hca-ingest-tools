#!/usr/bin/env python3
"""Temporary script to calculate SHA256 for test content."""

import hashlib

# Test content that will be used in our fixture
test_content = b"Hello, HCA World! This is a test file for checksum validation."

# Calculate SHA256
sha256_hash = hashlib.sha256()
sha256_hash.update(test_content)
result = sha256_hash.hexdigest()

print(f"Test content: {test_content}")
print(f"SHA256: {result}")
print(f"Length: {len(test_content)} bytes")
