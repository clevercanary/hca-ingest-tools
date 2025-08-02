"""
Redux CLI - A clean Typer playground following framework best practices.

This module demonstrates idiomatic Typer usage with proper type annotations,
following the patterns from the official Typer repository examples.
"""

from typing import Optional
import typer
from typing_extensions import Annotated

# Create the Typer app instance
app = typer.Typer(
    name="redux",
    help="A CLI playground for experimenting with Typer patterns",
    add_completion=False,  # Disable shell completion for simplicity
)


def main() -> None:
    """Entry point for the CLI application."""
    app()


@app.command()
def hello(
    name: Annotated[str, typer.Argument(help="The name to greet")] = "World",
    count: Annotated[int, typer.Option("--count", "-c", help="Number of greetings")] = 1,
    polite: Annotated[bool, typer.Option("--polite", "-p", help="Add please and thank you")] = False,
) -> None:
    """
    Say hello to someone.
    
    This is a simple greeting command that demonstrates:
    - Arguments with defaults
    - Options with short flags
    - Boolean flags
    - Type annotations using Annotated
    """
    greeting = "Hello"
    if polite:
        greeting = "Please allow me to say hello to"
    
    for i in range(count):
        if count > 1:
            typer.echo(f"{greeting} {name}! (#{i + 1})")
        else:
            typer.echo(f"{greeting} {name}!")
    
    if polite:
        typer.echo("Thank you for your time!")


@app.command()
def goodbye(
    name: Annotated[str, typer.Argument(help="The name to say goodbye to")] = "World",
    formal: Annotated[bool, typer.Option("--formal", "-f", help="Use formal language")] = False,
) -> None:
    """
    Say goodbye to someone.
    
    Demonstrates another simple command with different options.
    """
    if formal:
        typer.echo(f"Farewell, {name}. It was a pleasure.")
    else:
        typer.echo(f"Bye {name}!")


@app.command()
def info() -> None:
    """
    Show information about this CLI.
    
    Demonstrates a simple command with no arguments or options.
    """
    typer.echo("Redux CLI - A Typer playground")
    typer.echo("Version: 0.1.0")
    typer.echo("Built with Typer following framework best practices")


if __name__ == "__main__":
    main()
