# Redux CLI

A clean Typer playground for experimenting with CLI patterns and best practices.

## Purpose

This is a minimal CLI application built with Typer that demonstrates:
- Idiomatic Typer usage following official examples
- Proper type annotations with `Annotated`
- Clean command structure without Rich dependencies
- Framework-aligned patterns that work with Typer's design

## Installation

```bash
cd redux
poetry install
```

## Usage

```bash
# Basic greeting
poetry run redux hello

# Greeting with name
poetry run redux hello Alice

# Multiple greetings
poetry run redux hello Bob --count 3

# Polite greeting
poetry run redux hello Charlie --polite

# Goodbye command
poetry run redux goodbye Dave --formal

# Show info
poetry run redux info

# Help
poetry run redux --help
poetry run redux hello --help
```

## Development

```bash
# Install dependencies
poetry install

# Run the CLI
poetry run redux hello

# Run tests (when added)
poetry run pytest

# Type checking
poetry run mypy src

# Code formatting
poetry run black src
```

## Design Philosophy

This CLI follows Typer's idiomatic patterns:
- Uses `typer.echo()` instead of `print()` for output
- Uses `Annotated` for type hints with parameter metadata
- Follows the official Typer examples structure
- Minimal dependencies (just Typer, no Rich)
- Clean separation of concerns

## Commands

- `hello` - Greeting command with options for count and politeness
- `goodbye` - Farewell command with formal option
- `info` - Show CLI information

This serves as a foundation for experimenting with CLI patterns before applying them to more complex applications.
