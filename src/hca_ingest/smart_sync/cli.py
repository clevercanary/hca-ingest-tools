"""Command-line interface for HCA Smart Sync."""

import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from hca_ingest.config import Config
from hca_ingest.smart_sync.sync_engine import SmartSync

# Minimal Typer app
app = typer.Typer()
console = Console()

# Color constants for consistent styling
class Colors:
    RED = "[red]"
    GREEN = "[green]"
    RESET = "[/red]"
    GREEN_RESET = "[/green]"

# Message templates for consistent formatting
class Messages:
    # Error messages
    CONFIG_LOAD_ERROR = "Error loading configuration: {error}"
    CONFIG_INIT_ERROR = "Failed to initialize configuration: {error}"
    CONFIG_SHOW_ERROR = "Failed to load configuration: {error}"
    SYNC_ERROR = "Sync failed: {error}"
    BUCKET_NOT_CONFIGURED = "Error: S3 bucket not configured. Provide bucket argument or set in config"
    
    # Success messages
    CONFIG_INITIALIZING = "Initializing HCA Smart Sync Configuration"
    CONFIG_INITIALIZED = "Configuration initialized successfully"
    
    # Result states
    DRY_RUN_COMPLETED = "Dry run completed"
    SYNC_CANCELLED = "Sync canceled by user"
    SYNC_COMPLETED = "Sync completed successfully"

# Result message lookup table
RESULT_MESSAGES = {
    "dry_run": {
        "action": "Would upload",
        "status": Messages.DRY_RUN_COMPLETED,
        "show_file_count": False
    },
    "cancelled": {
        "action": "Uploaded",
        "status": Messages.SYNC_CANCELLED,
        "show_file_count": True
    },
    "completed": {
        "action": "Uploaded",
        "status": Messages.SYNC_COMPLETED, 
        "show_file_count": True
    }
}

# Common message helpers
def error_msg(message: str) -> str:
    """Format error message with consistent styling."""
    return f"{Colors.RED}{message}{Colors.RESET}"

def success_msg(message: str) -> str:
    """Format success message with consistent styling."""
    return f"{Colors.GREEN}{message}{Colors.GREEN_RESET}"

# Common formatting helpers
def format_file_count(file_count: int, action: str) -> str:
    """Format file count message with consistent styling."""
    return f"\n{action} {file_count} file(s)"

def format_status(status: str) -> str:
    """Format status message with consistent styling."""
    return f"[green]{status}[/green]"

# Configuration helpers
def _load_and_configure(profile: Optional[str], bucket: Optional[str]) -> Config:
    """Load configuration and apply overrides."""
    try:
        config = Config()
        if profile:
            config.aws.profile = profile
        if bucket:
            config.s3.bucket_name = bucket
        return config
    except Exception as e:
        console.print(error_msg(Messages.CONFIG_LOAD_ERROR.format(error=e)))
        raise typer.Exit(1)

def _validate_configuration(config: Config) -> None:
    """Validate required configuration settings."""
    if not config.s3.bucket_name:
        console.print(error_msg(Messages.BUCKET_NOT_CONFIGURED))
        raise typer.Exit(1)

def _build_s3_path(bucket_name: str, atlas: str, folder: str) -> str:
    """Build S3 path from components."""
    bionetwork = atlas.split('-')[0]
    return f"s3://{bucket_name}/{bionetwork}/{atlas}/{folder}/"

def _resolve_local_path(local_path: Optional[str]) -> Path:
    """Resolve local directory to scan."""
    if local_path:
        return Path(local_path).resolve()
    else:
        return Path.cwd()

def _initialize_sync_engine(config: Config, profile: Optional[str]) -> SmartSync:
    """Initialize sync engine with configuration."""
    sync_engine = SmartSync(config)
    
    # Reset AWS clients if profile was overridden to ensure new profile is used
    if profile:
        sync_engine._reset_aws_clients()
    
    return sync_engine

@app.command()
def sync(
    atlas: str = typer.Argument(help="Atlas name (e.g., gut-v1, immune-v1)"),
    dry_run: bool = typer.Option(False, help="Dry run mode"),
    verbose: bool = typer.Option(False, help="Verbose output"),
    profile: Optional[str] = typer.Option(None, help="AWS profile"),
    environment: str = typer.Option("prod", help="Environment: prod or dev (default: prod)"),
    folder: str = typer.Option("source-datasets", help="Target folder (default: source-datasets)"),
    force: bool = typer.Option(False, help="Force upload"),
    local_path: Optional[str] = typer.Option(None, help="Local directory to scan (defaults to current directory)"),
) -> None:
    """Sync .h5ad files from local directory to S3."""
    
    # Determine bucket based on environment
    if environment == "dev":
        bucket = "hca-atlas-tracker-data-dev"
    elif environment == "prod":
        bucket = "hca-atlas-tracker-data"
    else:
        console.print("[red]❌ Invalid environment. Must be 'prod' or 'dev'[/red]")
        raise typer.Exit(1)
    
    # Load and validate configuration
    config = _load_and_configure(profile, bucket)
    _validate_configuration(config)
    
    # Build paths
    s3_path = _build_s3_path(config.s3.bucket_name, atlas, folder)
    current_dir = _resolve_local_path(local_path)
    
    # Initialize sync engine and perform sync
    try:
        sync_engine = _initialize_sync_engine(config, profile)
        
        # Perform sync
        result = sync_engine.sync(
            local_path=current_dir,
            s3_path=s3_path,
            dry_run=dry_run,
            verbose=verbose,
            force=force,
        )
        
        # Display results
        _display_results(result, dry_run)
        
    except Exception as e:
        console.print(error_msg(Messages.SYNC_ERROR.format(error=e)))
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


def _display_results(result: dict, dry_run: bool) -> None:
    """Display sync results."""
    file_count = result.get('files_uploaded', 0)
    cancelled = result.get('cancelled', False)
    
    # Determine result state and get appropriate messages
    if dry_run:
        state = "dry_run"
    elif cancelled:
        state = "cancelled"
    else:
        state = "completed"
    
    msg = RESULT_MESSAGES[state]
    
    # Display file count if needed (consistent f-string formatting)
    if msg["show_file_count"]:
        console.print(format_file_count(file_count, msg["action"]))
    
    # Display status message (always green for success states)
    console.print(format_status(msg["status"]))
    console.print()  # Add spacing after results


def main() -> None:
    """Main entry point for the CLI."""
    try:
        app()
    except Exception as e:
        # Handle Click/Typer usage errors with clean messages
        error_msg = str(e)
        if ("Got unexpected extra arguments" in error_msg or 
            "TyperArgument.make_metavar()" in error_msg or
            "takes 1 positional argument but 2 were given" in error_msg):
            # Use basic print to avoid Rich formatting issues
            print()
            print("❌ Wrong number of arguments provided")
            print()
            print("Usage: hca-smart-sync sync <atlas> [options]")
            print()
            print("Examples:")
            print("  hca-smart-sync sync gut-v1 --profile my-profile")
            print("  hca-smart-sync sync immune-v1 --profile my-profile")
            print()
            exit(1)
        else:
            # Re-raise other exceptions
            raise


if __name__ == "__main__":
    main()
