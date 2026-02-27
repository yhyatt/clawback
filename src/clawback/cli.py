"""Click CLI entrypoint for Clawback."""

import sys

import click

from . import __version__
from .commands import CommandHandler
from .parser import parse_command
from .state import TripManager


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """Clawback - Token-efficient group expense splitting."""
    pass


@cli.command()
@click.argument("chat_id")
@click.argument("message", nargs=-1, required=True)
@click.option("--state-dir", default=None, help="State directory (default: ~/.clawback)")
@click.option("--sheets-account", default=None, help="Google account for Sheets sync")
@click.option("--no-sheets", is_flag=True, help="Disable Google Sheets integration")
def handle(
    chat_id: str,
    message: tuple[str, ...],
    state_dir: str | None,
    sheets_account: str | None,
    no_sheets: bool,
) -> None:
    """
    Handle a message from a chat.

    CHAT_ID is the unique identifier for the conversation.
    MESSAGE is the user's message text.
    """
    trip_manager = TripManager(state_dir)
    handler = CommandHandler(
        trip_manager,
        sheets_account=sheets_account,
        create_sheets=not no_sheets,
    )

    text = " ".join(message)
    response = handler.handle_message(chat_id, text)
    click.echo(response)


@cli.command()
@click.argument("text", nargs=-1, required=True)
def parse(text: tuple[str, ...]) -> None:
    """
    Parse a command without executing it.

    Useful for debugging the parser.
    """
    from .models import ParseError

    full_text = " ".join(text)
    result = parse_command(full_text)

    if isinstance(result, ParseError):
        click.echo(f"❌ Parse Error: {result.message}")
        click.echo(f"   Raw: {result.raw_text}")
        if result.suggestions:
            click.echo("   Suggestions:")
            for s in result.suggestions:
                click.echo(f"   • {s}")
        sys.exit(1)
    else:
        click.echo(f"✅ Parsed: {result.command_type.value}")
        for field, value in result.model_dump(exclude_none=True).items():
            if field not in ("command_type", "raw_text"):
                click.echo(f"   {field}: {value}")


@cli.command()
@click.option("--state-dir", default=None, help="State directory (default: ~/.clawback)")
def trips(state_dir: str | None) -> None:
    """List all trips."""
    trip_manager = TripManager(state_dir)
    trip_names = trip_manager.list_trips()

    if not trip_names:
        click.echo("No trips found.")
        return

    click.echo("Trips:")
    for name in trip_names:
        trip = trip_manager.get_trip(name)
        if trip:
            click.echo(f"  • {name} ({trip.base_currency}) - {len(trip.expenses)} expenses")


@cli.command()
@click.argument("trip_name")
@click.option("--state-dir", default=None, help="State directory (default: ~/.clawback)")
def balances(trip_name: str, state_dir: str | None) -> None:
    """Show balances for a trip."""
    from . import ledger, templates

    trip_manager = TripManager(state_dir)
    trip = trip_manager.get_trip(trip_name)

    if not trip:
        click.echo(f"Trip '{trip_name}' not found.")
        sys.exit(1)

    debts = ledger.simplified_debts(trip, trip.base_currency)

    if not debts:
        click.echo("✨ All settled up!")
        return

    click.echo(f"📊 {trip.name} Balances:\n")
    click.echo(templates.format_debts_list(debts, trip.base_currency))


@cli.command()
@click.option("--state-dir", default=None, help="State directory (default: ~/.clawback)")
def cleanup(state_dir: str | None) -> None:
    """Clean up expired pending confirmations."""
    trip_manager = TripManager(state_dir)
    count = trip_manager.cleanup_expired_pending()
    click.echo(f"Cleaned up {count} expired pending confirmation(s).")


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
