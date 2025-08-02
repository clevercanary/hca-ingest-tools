"""HCA Smart Sync - Intelligent S3 synchronization for HCA Atlas data."""

__version__ = "1.0.0"
__author__ = "HCA Team"
__email__ = "hca-team@example.com"

from hca_smart_sync.sync_engine import SmartSync
from hca_smart_sync.config import Config

__all__ = ["SmartSync", "Config", "__version__"]
