"""Tests for HCA Ingest Tools configuration."""

import os
from pathlib import Path

import pytest

from hca_smart_sync.config import Config, AWSConfig, S3Config


class TestConfig:
    """Test configuration management."""
    
    def test_config_creation(self):
        """Test basic configuration creation."""
        config = Config()
        
        assert config.aws is not None
        assert config.s3 is not None
        assert config.manifest is not None
        assert isinstance(config.config_dir, Path)
    
    def test_aws_config_defaults(self):
        """Test AWS configuration defaults."""
        aws_config = AWSConfig()
        
        assert aws_config.profile is None
        assert aws_config.region == "us-east-1"
        assert aws_config.access_key_id is None
        assert aws_config.secret_access_key is None
    
    def test_s3_config_defaults(self):
        """Test S3 configuration defaults."""
        s3_config = S3Config()
        
        assert s3_config.bucket_name is None
        assert s3_config.use_transfer_acceleration is True
        assert s3_config.multipart_threshold == 64 * 1024 * 1024
        assert s3_config.max_concurrency == 10
    
    def test_config_from_env(self, monkeypatch):
        """Test configuration from environment variables."""
        # Set test environment variables
        monkeypatch.setenv("HCA_AWS_PROFILE", "test-profile")
        monkeypatch.setenv("HCA_AWS_REGION", "us-west-2")
        monkeypatch.setenv("HCA_S3_BUCKET", "test-bucket")
        monkeypatch.setenv("HCA_VERBOSE", "true")
        
        config = Config.from_env()
        
        assert config.aws.profile == "test-profile"
        assert config.aws.region == "us-west-2"
        assert config.s3.bucket_name == "test-bucket"
        assert config.verbose is True
    
    def test_aws_session_kwargs(self):
        """Test AWS session kwargs generation."""
        config = Config()
        config.aws.profile = "test-profile"
        config.aws.region = "us-west-2"
        
        kwargs = config.get_aws_session_kwargs()
        
        assert kwargs["profile_name"] == "test-profile"
        assert kwargs["region_name"] == "us-west-2"
    
    def test_s3_client_kwargs(self):
        """Test S3 client kwargs generation."""
        config = Config()
        config.aws.access_key_id = "test-key"
        config.aws.secret_access_key = "test-secret"
        config.aws.region = "us-east-1"
        
        kwargs = config.get_s3_client_kwargs()
        
        assert kwargs["aws_access_key_id"] == "test-key"
        assert kwargs["aws_secret_access_key"] == "test-secret"
        assert kwargs["region_name"] == "us-east-1"
