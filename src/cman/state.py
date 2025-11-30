from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from requests.auth import HTTPBasicAuth

from cman import api
from cman.data import Card, Meta


def states_from_apply_diff(
    auth: HTTPBasicAuth,
    decks: Mapping[str, str],  # deck name -> mochi deck id
    state: dict[str, api.Card],
    diff: MochiDiff,
    meta: dict[Path, Meta],
) -> Iterator[tuple[dict[str, api.Card], dict[Path, Meta]]]:
    for id, card in diff.changed.items():
        u = api.update_card(
            auth,
            api.Card(
                id=id,
                content=card.content,
                deck_id=decks[card.deck_name],
            ),
            attachments=card.attachments,
        )
        state[u.id] = u
        yield state, meta

    for card in diff.removed:
        api.delete_card(auth, card.id)
        state.pop(card.id)
        yield state, meta

    for card in diff.new:
        u = api.create_card(auth, decks[card.deck_name], card.content, card.attachments)
        meta.setdefault(card.path, Meta(None, None)).set_by_direction(
            card.direction, u.id
        )
        state[u.id] = u
        yield state, meta


@dataclass
class MochiDiff:
    changed: dict[str, Card]
    removed: list[api.Card]
    new: list[Card]

    @classmethod
    def from_states(
        cls,
        remote: dict[str, api.Card],
        existing: dict[str, Card],
        new: list[Card],
        decks: Mapping[str, str],  # deck name -> mochi deck id
    ):
        assert set(existing) <= set(remote), "Remote deletion is not supported."
        changed = {
            id: card
            for id, card in existing.items()
            # TODO not very happy with the comparison here
            # content contains the image hashes, so content is enough to compare to also detect image changes
            # but deck_name is separate so we need to compare it, how to deal with things that we might add?
            if (remote[id].content != card.content)
            or (remote[id].deck_id != decks[card.deck_name])
        }
        removed = [c for c in remote.values() if c.id not in existing]
        return cls(changed, removed, new)

    def count(self) -> int:
        return len(self.changed) + len(self.removed) + len(self.new)

    def print_summary(self):
        for c in self.changed.values():
            print(f"changed from {c.path}")
        for c in self.new:
            print(f"new from {c.path}")
        print(
            f"{self.count()} items in diff: "
            f"{len(self.removed)} removed, "
            f"{len(self.changed)} changed, "
            f"{len(self.new)} new cards"
        )
