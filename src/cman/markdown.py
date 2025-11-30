"""
pandoc is pretty good
but the type annotations dont work with pyright
because they are non-standard and generated
so we put all "unsafe" code here behind a
type-safe interface for the rest of the code base
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pandoc
from pandoc.types import (
    Block,  # pyright: ignore
    Emph,  # pyright: ignore
    HorizontalRule,  # pyright: ignore
    Image,  # pyright: ignore
    Inline,  # pyright: ignore
    Meta,  # pyright: ignore
    Pandoc,  # pyright: ignore
    Para,  # pyright: ignore
    Space,  # pyright: ignore
    Str,  # pyright: ignore
)


class Direction(Enum):
    forward = "forward"
    backward = "backward"


@dataclass
class Markdown:
    body: list[Block]

    @classmethod
    def from_str(cls, text: str):
        _, body = pandoc.read(text, format="markdown")  # pyright: ignore
        assert type(body) is list, type(body)
        return cls(body)

    @classmethod
    def from_path(cls, path: Path):
        return cls.from_str(path.read_text())

    def as_mochi_md_str(self) -> str:
        data = pandoc.write(
            Pandoc(Meta({}), self.body),
            format="markdown+hard_line_breaks",
            # NOTE columns=3 and wrap=none forces rulers to be exactly 3 dashes (---)
            # mochi accepts only exactly 3 dashes (---) as a new page
            options=["--columns=3", "--wrap=none"],
        )
        # TODO note sure in what case we get what
        assert type(data) is str, type(data)
        return data

    def as_formatted(self) -> str:
        formatted = pandoc.write(
            Pandoc(Meta({}), self.body),  # pyright: ignore[reportAttributeAccessIssue]
            # NOTE this is the format i use in nvim too
            format="markdown",
        )
        assert type(formatted) is str, type(formatted)
        return formatted

    def reversed(self) -> Markdown:
        first, second = split_blocks(self.body)
        return Markdown(second + [HorizontalRule()] + first)

    def oriented(self, direction: Direction) -> Markdown:
        match direction:
            case Direction.forward:
                return self
            case Direction.backward:
                return self.reversed()
            case _:
                assert False

    def has_reverse_prompt(self) -> bool:
        _, answer = split_blocks(self.body)
        prompts = [b for b in map(maybe_match_prompt, answer) if b is not None]
        match prompts:
            case []:
                return False
            case [_]:
                return True
            case _:
                assert False, prompts

    def maybe_prompted(self) -> Markdown:
        question, answer = split_blocks(self.body)

        def f(block: Block):
            prompt = maybe_match_prompt(block)
            if prompt is None:
                return block
            return Para([Emph(prompt)])

        question = [f(b) for b in question]

        def g(block: Block):
            prompt = maybe_match_prompt(block)
            if prompt is None:
                return block
            return None

        answer = [b for b in map(g, answer) if b is not None]
        return Markdown(question + [HorizontalRule()] + answer)

    def with_rewritten_images(
        self, transform: Callable[[str], tuple[str, str]]
    ) -> Markdown:
        body = deepcopy(self.body)
        for block in pandoc.iter(body):
            match block:
                case Image(_, _, (path, _)):
                    # TODO what happens to the iter if we change things as we go?
                    block[2] = transform(path)
        return Markdown(body)

    def get_image_paths(self) -> list[Path]:
        def g() -> Iterator[Path]:
            for block in pandoc.iter(self.body):
                match block:
                    case Image(_, _, (path, _)):
                        yield Path(path)

        return list(g())


def split_blocks(blocks: list[Block]) -> tuple[list[Block], list[Block]]:
    [split] = [i for i, e in enumerate(blocks) if e == HorizontalRule()]
    return blocks[:split], blocks[split + 1 :]


def maybe_match_prompt(block: Block) -> None | list[Inline]:
    match block:
        # TODO is ! even okay? or does it clash with ![]() for images?
        case Para([Str("!" | "prompt:" | "Prompt:"), Space(), *prompt]):
            return prompt
        case _:
            return None
