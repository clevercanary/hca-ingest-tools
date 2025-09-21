"""Configuration management for HCA Ingest Tools."""

import os
from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings


class AWSConfig(BaseModel):
    """AWS configuration settings."""
    
    profile: Optional[str] = Field(default=None, description="AWS profile name")
    region: str = Field(default="us-east-1", description="AWS region")
    access_key_id: Optional[str] = Field(default=None, description="AWS access key ID")
    secret_access_key: Optional[str] = Field(default=None, description="AWS secret access key")


class S3Config(BaseModel):
    """S3-specific configuration."""
    
    bucket_name: Optional[str] = Field(default=None, description="Default S3 bucket name")
    use_transfer_acceleration: bool = Field(default=True, description="Use S3 transfer acceleration")
    multipart_threshold: int = Field(default=64 * 1024 * 1024, description="Multipart upload threshold in bytes")
    max_concurrency: int = Field(default=10, description="Maximum concurrent uploads")


class ManifestConfig(BaseModel):
    """Manifest generation configuration."""
    
    include_checksums: bool = Field(default=True, description="Include SHA256 checksums in manifest")
    include_metadata: bool = Field(default=True, description="Include file metadata in manifest")
    manifest_filename: str = Field(default="submission_manifest.json", description="Default manifest filename")


class Config(BaseSettings):
    """Main configuration class for HCA Ingest Tools."""
    
    # AWS Configuration
    aws: AWSConfig = Field(default_factory=AWSConfig, description="AWS configuration")
    s3: S3Config = Field(default_factory=S3Config, description="S3 configuration")
    manifest: ManifestConfig = Field(default_factory=ManifestConfig, description="Manifest configuration")
    
    # Tool Configuration
    verbose: bool = Field(default=False, description="Enable verbose logging")
    dry_run: bool = Field(default=False, description="Perform dry run without actual uploads")
    config_dir: Path = Field(
        default_factory=lambda: Path.home() / ".config" / "hca-ingest-tools",
        description="Configuration directory"
    )
    
    model_config = ConfigDict(
        env_prefix="HCA_",
        env_nested_delimiter="__",
        case_sensitive=False
    )
    
    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables."""
        return cls(
            aws=AWSConfig(
                profile=os.getenv("HCA_AWS_PROFILE") or os.getenv("AWS_PROFILE"),
                region=os.getenv("HCA_AWS_REGION", "us-east-1"),
                access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            ),
            s3=S3Config(
                bucket_name=os.getenv("HCA_S3_BUCKET"),
                use_transfer_acceleration=os.getenv("HCA_S3_TRANSFER_ACCELERATION", "true").lower() == "true",
            ),
            manifest=ManifestConfig(
                include_checksums=os.getenv("HCA_MANIFEST_INCLUDE_CHECKSUMS", "true").lower() == "true",
                include_metadata=os.getenv("HCA_MANIFEST_INCLUDE_METADATA", "true").lower() == "true",
                manifest_filename=os.getenv("HCA_MANIFEST_FILENAME", "submission_manifest.json"),
            ),
            verbose=os.getenv("HCA_VERBOSE", "false").lower() == "true",
            dry_run=os.getenv("HCA_DRY_RUN", "false").lower() == "true",
        )
    
    def ensure_config_dir(self) -> None:
        """Ensure configuration directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def get_aws_session_kwargs(self) -> Dict[str, str]:
        """Get AWS session kwargs for boto3."""
        kwargs = {}
        
        if self.aws.profile:
            kwargs["profile_name"] = self.aws.profile
        
        if self.aws.region:
            kwargs["region_name"] = self.aws.region
            
        return kwargs
    
    def get_s3_client_kwargs(self) -> Dict[str, any]:
        """Get S3 client configuration kwargs."""
        kwargs = {}
        
        if self.aws.access_key_id and self.aws.secret_access_key:
            kwargs["aws_access_key_id"] = self.aws.access_key_id
            kwargs["aws_secret_access_key"] = self.aws.secret_access_key
        
        if self.aws.region:
            kwargs["region_name"] = self.aws.region
            
        return kwargs


# Global configuration instance
config = Config.from_env()
