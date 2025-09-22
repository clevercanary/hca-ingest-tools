"""Manifest generation for HCA data submissions."""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from natsort import natsorted
from hca_smart_sync.checksum import ChecksumCalculator


class ManifestGenerator:
    """Generate submission manifests for HCA data uploads."""
    
    def __init__(self):
        """Initialize the manifest generator."""
        self.checksum_calculator = ChecksumCalculator()
    
    def generate_manifest(
        self,
        files: List[Path],
        metadata: Optional[Dict] = None,
        submitter_info: Optional[Dict] = None,
    ) -> Dict:
        """
        Generate a submission manifest for uploaded files.
        
        Args:
            files: List of files that were uploaded
            metadata: Additional metadata to include
            submitter_info: Information about the submitter
            
        Returns:
            Dictionary containing the manifest data
        """
        manifest = {
            "manifest_version": "1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "submission_id": self._generate_submission_id(),
            "files": [],
            "metadata": metadata or {},
            "submitter": submitter_info or {},
        }
        
        # Sort files using natural sorting for consistent ordering
        sorted_files = natsorted(files, key=lambda x: x.name)
        
        # Add file information
        for file_path in sorted_files:
            if file_path.exists():
                file_info = {
                    "filename": file_path.name,
                    "size_bytes": file_path.stat().st_size,
                    "sha256": self.checksum_calculator.calculate_sha256(file_path),
                    "modified_at": datetime.fromtimestamp(
                        file_path.stat().st_mtime
                    ).isoformat() + "Z",
                }
                manifest["files"].append(file_info)
        
        return manifest
    
    def save_manifest(self, manifest: Dict, output_path: Path) -> None:
        """
        Save the manifest to a JSON file.
        
        Args:
            manifest: The manifest dictionary
            output_path: Path where to save the manifest
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    def generate_manifest_filename(self) -> str:
        """
        Generate a human-readable manifest filename with timestamp down to milliseconds.
        
        Returns:
            Filename in format: manifest-2025-01-30-02-31-19-123.json
        """
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d-%H-%M-%S")
        milliseconds = f"{now.microsecond // 1000:03d}"
        return f"manifest-{timestamp}-{milliseconds}.json"
    
    def _generate_submission_id(self) -> str:
        """Generate a unique submission ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"submission_{timestamp}"
