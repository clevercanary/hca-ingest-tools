"""HCA Ingest Tools - Tools for ingesting biological data into HCA infrastructure."""

__version__ = "0.1.0"
__author__ = "HCA Team"
__email__ = "hca-team@example.com"

from hca_ingest.smart_sync import SmartSync
from hca_ingest.config import Config

__all__ = ["SmartSync", "Config", "__version__"]
