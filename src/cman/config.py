from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from serde import serde
from serde.toml import from_toml


@serde
@dataclass
class Config:
    # where the cards are
    # the path can be absolute, but relative is interpreted relative to the file
    path: Path

    # maps folders relative to self.path to deck ids
    # just one level hierarchy
    # NOTE only folder that are mentioned here are synced
    decks: dict[str, str]

    @classmethod
    def from_base(cls, base: Path):
        return from_toml(cls, (base / "config.toml").read_text())


@serde
@dataclass
class Mochi:
    token: str


@serde
@dataclass
class Credentials:
    mochi: Mochi

    @classmethod
    def from_base(cls, base: Path):
        return from_toml(cls, (base / "credentials.toml").read_text())
