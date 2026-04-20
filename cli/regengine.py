#!/usr/bin/env python3
"""
RegEngine CLI
=============
Command-line interface for RegEngine operations.

Commands:
- validate vertical <name>: Validate vertical schemas
- list-verticals: List all available verticals

NOTE: The ``compile vertical`` command and the entire kernel/control compiler
stack have been retired (Option B, #1366). The codegen stack had 14 known
defects including code-injection via f-string generation (#1285). It will be
re-introduced properly during the 6-services→1-monolith migration.
"""

import click
import sys
from pathlib import Path
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@click.group()
def cli():
    """RegEngine - Regulatory Compliance Engine CLI"""
    pass


@cli.group()
def validate():
    """Validation commands"""
    pass


@validate.command('vertical')
@click.argument('vertical_name')
@click.option('--verticals-dir', default='./verticals', help='Path to verticals directory')
def validate_vertical(vertical_name: str, verticals_dir: str):
    """
    Validate a vertical's YAML schemas without compiling.

    Checks:
    - vertical.yaml structure
    - obligations.yaml completeness
    - Cross-validation (evidence_contract, scoring_weights)

    Example:
        regengine validate vertical finance
    """
    click.echo(f"Validating vertical: {vertical_name}")
    click.echo("")

    try:
        import yaml

        verticals_path = Path(verticals_dir)
        vertical_dir = verticals_path / vertical_name

        # Load vertical.yaml
        vertical_file = vertical_dir / "vertical.yaml"
        if not vertical_file.exists():
            click.echo(f"ERROR: vertical.yaml not found at {vertical_file}")
            sys.exit(1)

        with open(vertical_file) as f:
            vertical_data = yaml.safe_load(f)

        click.echo("OK: vertical.yaml found")

        # Load obligations.yaml
        obligations_file = vertical_dir / "obligations.yaml"
        if not obligations_file.exists():
            click.echo(f"ERROR: obligations.yaml not found at {obligations_file}")
            sys.exit(1)

        with open(obligations_file) as f:
            obligations_data = yaml.safe_load(f)

        click.echo("OK: obligations.yaml found")
        click.echo("")
        click.echo("Summary:")
        click.echo(f"  {len(obligations_data.get('obligations', []))} obligations defined")
        click.echo(f"  {len(vertical_data.get('regulators', []))} regulators")
        click.echo(f"  {len(vertical_data.get('decision_types', []))} decision types")

        sys.exit(0)

    except Exception as e:
        click.echo(f"ERROR: Validation error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command('list-verticals')
@click.option('--verticals-dir', default='./verticals', help='Path to verticals directory')
def list_verticals(verticals_dir: str):
    """List all available verticals."""
    click.echo("Available verticals:")
    click.echo("")

    verticals_path = Path(verticals_dir)

    if not verticals_path.exists():
        click.echo(f"ERROR: Verticals directory not found: {verticals_path}")
        sys.exit(1)

    verticals = []
    for item in verticals_path.iterdir():
        if item.is_dir() and (item / "vertical.yaml").exists():
            verticals.append(item.name)

    if not verticals:
        click.echo("  No verticals found")
    else:
        for vertical in sorted(verticals):
            click.echo(f"  - {vertical}")

    click.echo("")
    click.echo(f"Total: {len(verticals)} vertical(s)")


if __name__ == '__main__':
    cli()
