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


@app.command()
def sync(
    atlas: str = typer.Argument(help="Atlas name (e.g., gut-v1, immune-v1)"),
    bucket: Optional[str] = typer.Argument(None, help="S3 bucket name"),
    folder: str = typer.Argument("source-datasets", help="Target folder"),
    dry_run: bool = typer.Option(False, help="Dry run mode"),
    verbose: bool = typer.Option(False, help="Verbose output"),
    profile: Optional[str] = typer.Option(None, help="AWS profile"),
    force: bool = typer.Option(False, help="Force upload"),
    local_path: Optional[str] = typer.Option(None, help="Local directory to scan (defaults to current directory)"),
) -> None:
    """Sync .h5ad files from local directory to S3."""
    
    # Load configuration
    try:
        config = Config()
        if profile:
            config.aws.profile = profile
        if bucket:
            config.s3.bucket_name = bucket
    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        raise typer.Exit(1)
    
    # Validate required configuration
    if not config.s3.bucket_name:
        console.print("[red]Error: S3 bucket not configured. Provide bucket argument or set in config[/red]")
        raise typer.Exit(1)
    
    # Build S3 path
    bionetwork = atlas.split('-')[0]
    s3_path = f"s3://{config.s3.bucket_name}/{bionetwork}/{atlas}/{folder}/"
    
    # Determine local directory to scan
    if local_path:
        # Use provided local path
        current_dir = Path(local_path).resolve()
    else:
        # Use current working directory
        current_dir = Path.cwd()
    
    # Initialize sync engine
    try:
        sync_engine = SmartSync(config)
        
        # Reset AWS clients if profile was overridden to ensure new profile is used
        if profile:
            sync_engine._reset_aws_clients()
        
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
        console.print(f"[red]Sync failed: {e}[/red]")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def init() -> None:
    """Initialize configuration for HCA Smart Sync."""
    console.print("Initializing HCA Smart Sync Configuration")
    
    try:
        config = Config()
        console.print("[green]Configuration initialized successfully[/green]")
        _display_config(config)
    except Exception as e:
        console.print(f"[red]Failed to initialize configuration: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def config_show() -> None:
    """Show current configuration."""
    try:
        config = Config()
        _display_config(config)
    except Exception as e:
        console.print(f"[red]Failed to load configuration: {e}[/red]")
        raise typer.Exit(1)


def _display_config(
    config: Config, 
    local_path: Optional[Path] = None, 
    s3_path: Optional[str] = None,
    atlas: Optional[str] = None,
    folder: Optional[str] = None
) -> None:
    """Display current configuration."""
    table = Table(title="HCA Smart Sync Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("AWS Profile", config.aws.profile or "default")
    table.add_row("AWS Region", config.aws.region)
    table.add_row("S3 Bucket", config.s3.bucket_name or "Not configured")
    
    if atlas:
        table.add_row("Atlas", atlas)
    if folder:
        table.add_row("Target Folder", folder)
    if local_path:
        table.add_row("Local Path", str(local_path))
    if s3_path:
        table.add_row("S3 Path", s3_path)
    
    console.print(table)


def _display_results(result: dict, dry_run: bool) -> None:
    """Display sync results."""
    action = "Would upload" if dry_run else "Uploaded"
    file_count = result.get('files_uploaded', 0)
    cancelled = result.get('cancelled', False)
    
    if dry_run:
        console.print("\n[green]Dry run completed[/green]")
        console.print()
    elif cancelled:
        console.print("\n" + action + " " + str(file_count) + " file(s)", highlight=False)
        console.print("[green]Sync canceled by user[/green]")
        console.print()
    else:
        console.print("\n" + action + " " + str(file_count) + " file(s)", highlight=False)
        console.print("[green]Sync completed successfully[/green]")
        console.print()


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
