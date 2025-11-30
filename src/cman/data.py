from __future__ import annotations

import sys
from collections.abc import Set
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from shutil import copyfile

import typer
from PIL import Image
from serde import serde
from serde.json import from_json, to_json
from tqdm import tqdm

from cman.api import Attachment
from cman.markdown import Direction, Markdown


# TODO same name as api.Card ... can we have a better name here?
@dataclass
class Card:
    content: str
    deck_name: str
    attachments: list[Attachment]
    path: Path
    direction: Direction


@serde
class Meta:
    forward: None | str
    backward: None | str

    def set_by_direction(self, direction: Direction, value: None | str):
        match direction:
            case Direction.forward:
                self.forward = value
            case Direction.backward:
                self.backward = value
            case _:
                assert False

    def get_by_direction(self, direction: Direction) -> None | str:
        match direction:
            case Direction.forward:
                return self.forward
            case Direction.backward:
                return self.backward
            case _:
                assert False


def read_markdowns(base: Path, decks: Set[str]) -> dict[Path, Markdown]:
    """return paths are relative to base"""
    paths = [path for deck in decks for path in (base / deck).rglob("*.md")]
    return {
        path.relative_to(base): Markdown.from_path(path)
        for path in tqdm(paths, desc="read markdowns")
    }


def read_meta(base: Path) -> dict[Path, Meta]:
    at = base / "meta.json"
    if not at.exists():
        return {}
    meta_str = from_json(dict[str, Meta], at.read_text())
    meta = {Path(p): m for p, m in meta_str.items()}
    return meta


def write_meta(base: Path, meta: dict[Path, Meta]):
    # NOTE we sort it so that it's a bit more stable in a potential git diff
    meta_str = {str(p): m for p, m in sorted(meta.items())}
    (base / "meta.json").write_text(to_json(meta_str, indent=4))


def get_synced_meta(
    markdowns: dict[Path, Markdown], meta: dict[Path, Meta]
) -> dict[Path, Meta]:
    def f(path: Path, markdown: Markdown) -> Meta:
        if path not in meta:
            return Meta(None, None)
        return Meta(
            forward=meta[path].forward,
            backward=meta[path].backward if markdown.has_reverse_prompt() else None,
        )

    return {
        path: f(path, markdown)
        for path, markdown in tqdm(markdowns.items(), desc="sync local meta")
    }


def as_flat_meta_state(state: dict[Path, Meta]) -> set[tuple[Path, Direction, str]]:
    return {
        (path, direction, id)
        for path, meta in state.items()
        for direction in Direction
        if (id := meta.get_by_direction(direction)) is not None
    }


@dataclass
class MetaDiff:
    changes: list[tuple[Path, Direction, str | None, str | None]]

    @classmethod
    def from_states(cls, state: dict[Path, Meta], target: dict[Path, Meta]):
        changes = []
        for path in set(state) | set(target):
            for direction in Direction:
                now = state.get(path, Meta(None, None)).get_by_direction(direction)
                later = target.get(path, Meta(None, None)).get_by_direction(direction)
                if now != later:
                    changes.append((path, direction, now, later))
        return cls(changes)

    def print_summary(self):
        for path, direction, now, then in self.changes:
            print(f"{path} {direction.value} {now} -> {then}")

    def count(self) -> int:
        return len(self.changes)


def get_cards(
    base: Path, markdowns: dict[Path, Markdown], meta: dict[Path, Meta]
) -> tuple[dict[str, Card], list[Card]]:
    existing_cards: dict[str, Card] = dict()
    new_cards: list[Card] = []

    for path, markdown in tqdm(markdowns.items(), desc="make cards"):
        images = Images.from_base(base / path.parent)
        markdown = markdown.with_rewritten_images(images.collect)

        card = Card(
            content=markdown.maybe_prompted().as_mochi_md_str(),
            deck_name=path.parts[0],
            attachments=images.as_api_attachments(),
            path=path,
            direction=Direction.forward,
        )

        match meta.get(path, Meta(None, None)).forward:
            case None:
                new_cards.append(card)
            case str(card_id):
                assert card_id not in existing_cards, card_id
                existing_cards[card_id] = card
            case _ as never:
                assert_never(never)

        if markdown.has_reverse_prompt():
            card = Card(
                content=markdown.reversed().maybe_prompted().as_mochi_md_str(),
                deck_name=path.parts[0],
                attachments=images.as_api_attachments(),
                path=path,
                direction=Direction.backward,
            )

            match meta.get(path, Meta(None, None)).backward:
                case None:
                    new_cards.append(card)
                case str(card_id):
                    assert card_id not in existing_cards, card_id
                    existing_cards[card_id] = card
                case _ as never:
                    assert_never(never)

    return existing_cards, new_cards


@dataclass
class Images:
    base: Path
    next_index: int
    data: dict[str, bytes]
    max_width: int = 800

    @classmethod
    def from_base(cls, base: Path):
        return cls(base, 0, {})

    def collect(self, path: str) -> tuple[str, str]:
        local = self.base / path
        # TODO mochis requirements on names here a bit arbitrary, and not correctly documented too
        name = f"i{self.next_index:08}.png"
        remote = f"@media/{name}"
        self.next_index += 1

        with Image.open(local) as image:
            if image.width > self.max_width:
                height = round(image.height * self.max_width / image.width)
                image = image.resize((self.max_width, height))
            data = BytesIO()
            image.save(data, "png")
            self.data[name] = data.getvalue()

        hash = sha256()
        hash.update(self.data[name])

        return remote, hash.hexdigest()

    def as_api_attachments(self) -> list[Attachment]:
        return [Attachment(name, data) for name, data in self.data.items()]


def move(base: Path, source: Path, target: Path):
    """
    this is verbose and validates things
    can be used to move and/or rename
    """

    if not source.exists():
        print("Source does not exist.", file=sys.stderr)
        raise typer.Abort()

    if target.exists():
        print(f"Target {target} already exists.", file=sys.stderr)
        raise typer.Abort()

    # NOTE we need to resolve everything so that we can compute relative paths reliably
    base = base.resolve(strict=True)
    try:
        based_source = source.resolve(strict=True).relative_to(base)
        based_target = target.resolve(strict=False).relative_to(base)
    except ValueError:
        print(
            f"Source {source} and target {target} must be inside base {base}.",
            file=sys.stderr,
        )
        raise typer.Abort()

    if based_source == based_target:
        print("Source and target cannot be the same.", file=sys.stderr)
        raise typer.Abort()

    meta = read_meta(base)

    if based_source not in meta:
        print(f"Source {based_source} is not in {base / 'meta.json'}.", file=sys.stderr)
        raise typer.Abort()

    meta[based_target] = meta.pop(based_source)

    image_paths = Markdown.from_path(base / based_source).get_image_paths()
    if based_source.parent != based_target.parent:
        for ip in image_paths:
            if (base / based_target.parent / ip).exists():
                print(
                    f"Image at {base / based_target.parent / ip} already exists.",
                    file=sys.stderr,
                )
                raise typer.Abort()

    print(f"{base / based_source} -> {base / based_target}")
    copyfile(base / based_source, base / based_target)
    if based_source.parent != based_target.parent:
        for ip in image_paths:
            print(
                f"{base / based_source.parent / ip} -> {base / based_target.parent / ip}"
            )
            copyfile(base / based_source.parent / ip, base / based_target.parent / ip)

    (base / based_source).unlink()
    for ip in image_paths:
        (base / based_source.parent / ip).unlink()

    write_meta(base, meta)
