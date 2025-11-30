import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer


class state:
    base: Path = Path("./data")


app = typer.Typer(pretty_exceptions_enable=True, no_args_is_help=True)


@app.callback()
def main(base: Path):
    state.base = base


@app.command()
def sync():
    from cards.config import Config, Credentials
    from cards.sync import sync

    config = Config.from_base(state.base)
    credentials = Credentials.from_base(state.base)

    sync(credentials.mochi.token, state.base / config.path, config.decks)


@app.command()
def preview():
    from cards.config import Config
    from cards.preview import main

    config = Config.from_base(state.base)

    main(state.base / config.path)


@app.command()
def backup():
    """backup all cards of the configured decks, raw, as json"""
    from cards.backup import backup_deck
    from cards.config import Config, Credentials

    config = Config.from_base(state.base)
    credentials = Credentials.from_base(state.base)

    for deck_name, deck_id in config.decks.items():
        backup_deck(credentials.mochi.token, deck_name, deck_id)


@app.command()
def rename(
    source: Path,
    name: str,
    edit: Annotated[bool, typer.Option("--edit/--no-edit", "-e")] = False,
):
    """
    only renames, does not move, file stays in the same place
    NOTE only renames md files that are also in the meta.json, but not other connected files like images
    """
    from cards.data import move

    target = source.with_name(name)
    move(state.base, source, target)

    if edit:
        subprocess.run(["nvim", str(target)], check=True)


@app.command()
def move(source: Path, deck: str):
    """
    this does not rename, but only moves it to another deck
    card id stays the same
    only cards that exist in meta.json can be moved
    images are also moved
    """
    from cards.config import Config
    from cards.data import move

    config = Config.from_base(state.base)

    if deck not in config.decks:
        print(f"Deck {deck} does not exist.", file=sys.stderr)
        raise typer.Abort()

    try:
        based_source = source.resolve(strict=True).relative_to(
            state.base.resolve(strict=True)
        )
    except ValueError:
        print(
            f"Source {source} must be inside base {state.base}.",
            file=sys.stderr,
        )
        raise typer.Abort()

    target = state.base / deck / Path(*based_source.parts[1:])
    move(state.base, source, target)


@app.command()
def show(path: Path):
    """show some info about a card"""
    from cards.markdown import Markdown

    txt = path.read_text()
    md = Markdown.from_str(txt)
    formatted = md.as_formatted()

    print(formatted)

    print()
    if txt.strip() == formatted.strip():
        print("File is formatted.")
    else:
        print("File is not formatted.")

    print()
    for path in md.get_image_paths():
        print(f"image at {path}")


@app.command()
def fetch(card_id: str):
    from pprint import pp

    from cards.api import auth_from_token, raw_retrieve_card
    from cards.config import Credentials

    credentials = Credentials.from_base(state.base)
    auth = auth_from_token(credentials.mochi.token)

    card = raw_retrieve_card(auth, card_id)

    pp(card)
