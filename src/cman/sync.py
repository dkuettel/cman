from collections.abc import Mapping
from pathlib import Path

import click
from tqdm import tqdm

from cman.api import auth_from_token, list_cards
from cman.data import (
    MetaDiff,
    get_cards,
    get_synced_meta,
    read_markdowns,
    read_meta,
    write_meta,
)
from cman.state import MochiDiff, states_from_apply_diff


def sync(token: str, base: Path, decks: Mapping[str, str]):
    auth = auth_from_token(token)

    markdowns = read_markdowns(base, decks.keys())
    meta = read_meta(base)

    synced_meta = get_synced_meta(markdowns, meta)
    meta_diff = MetaDiff.from_states(meta, synced_meta)
    meta_diff.print_summary()
    if meta_diff.count() > 0:
        click.confirm("Continue?", abort=True)
        write_meta(base, synced_meta)
        meta = synced_meta

    existing_cards, new_cards = get_cards(base, markdowns, meta)

    remote = {
        c.id: c
        for c in tqdm(
            list_cards(auth),
            total=len(existing_cards),
            desc=f"list cards",
        )
    }
    for card in remote.values():
        assert not card.archived, card.id
        assert card.trashed is None, card.id
        assert not card.review_reverse, card.id
        assert card.template_id is None, card.id

    diff = MochiDiff.from_states(remote, existing_cards, new_cards, decks)
    diff.print_summary()

    if diff.count() > 0:
        click.confirm("Continue?", abort=True)
        for state, meta in tqdm(
            states_from_apply_diff(auth, decks, remote, diff, meta),
            total=diff.count(),
            desc="sync",
        ):
            assert len(state) > 0
            write_meta(base, meta)
