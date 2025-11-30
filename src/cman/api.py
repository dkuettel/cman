"""
implement relevant parts of
https://mochi.cards/docs/api/
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import requests
from pydantic import BaseModel, ConfigDict, Field
from requests.auth import HTTPBasicAuth


def url_at(at: str) -> str:
    return f"https://app.mochi.cards/api/{at}"


def model_config():
    return ConfigDict(
        alias_generator=lambda x: x.replace("_", "-"),
        populate_by_name=True,
        strict=True,
    )


def body_from_model(m: BaseModel, exclude: None | set[str] = None) -> dict:
    # TODO I dont like the options here, if that's always good, exclude_defaults
    # see comment down in raw_update_card
    return m.model_dump(by_alias=True, exclude_defaults=True, exclude=exclude)


@dataclass
class Attachment:
    file_name: str
    binary_data: bytes

    @classmethod
    def from_file(cls, file_name: str, path: Path):
        return cls(
            file_name,
            path.read_bytes(),
        )


class Card(BaseModel):
    model_config = model_config()

    id: str
    content: str
    deck_id: str
    archived: bool = Field(default=False, alias="archived?")
    trashed: None | str = Field(default=None, alias="trashed?")
    review_reverse: bool = Field(default=False, alias="review-reverse?")
    template_id: None | str = None


def iterate_paged_docs(auth: HTTPBasicAuth, url: str, params: dict) -> Iterator[dict]:
    limit = 100
    page_params = {"limit": limit}
    while True:
        response = requests.get(url, params={**params, **page_params}, auth=auth)
        assert response.status_code == 200, response.text
        response_json = response.json()
        bookmark = response_json["bookmark"]
        docs = response_json["docs"]
        yield from docs
        # TODO len(docs) < limit would be best
        # but the api doesnt complain if you use a too high limit
        # so len(docs) == 0 is the only robust way I can see, but uses an extra request
        if len(docs) == 0:
            break
        page_params["bookmark"] = bookmark


def raw_list_cards(auth: HTTPBasicAuth, deck_id: None | str = None) -> Iterator[dict]:
    url = url_at("cards")
    params = {}
    if deck_id is not None:
        params["deck-id"] = deck_id
    # TODO now deal with tqdm higher up, where we might have some len() estimate
    return iterate_paged_docs(auth, url, params)


def list_cards(auth: HTTPBasicAuth, deck_id: None | str = None) -> Iterator[Card]:
    for doc in raw_list_cards(auth, deck_id):
        yield Card(**doc)


def raw_create_card(auth: HTTPBasicAuth, deck_id: str, content: str) -> dict:
    url = url_at("cards")
    body = {
        "deck-id": deck_id,
        "content": content,
    }
    response = requests.post(url, json=body, auth=auth)
    assert response.status_code == 200, response.text
    return response.json()


def create_card(
    auth: HTTPBasicAuth, deck_id: str, content: str, attachments: list[Attachment]
) -> Card:
    card = Card(**raw_create_card(auth, deck_id, content))
    for attachment in attachments:
        raw_update_attachment(auth, card.id, attachment)
    return card


def raw_retrieve_card(auth: HTTPBasicAuth, card_id: str) -> dict:
    url = url_at(f"cards/{card_id}")
    response = requests.get(url, auth=auth)
    assert response.status_code == 200, response.text
    return response.json()


def retrieve_card(auth: HTTPBasicAuth, card_id: str) -> Card:
    return Card(**raw_retrieve_card(auth, card_id))


def raw_update_attachment(auth: HTTPBasicAuth, id: str, attachment: Attachment):
    url = url_at(f"cards/{id}/attachments/{attachment.file_name}")
    response = requests.post(url, files={"file": attachment.binary_data}, auth=auth)
    assert response.status_code == 200, response.text


def raw_update_card(auth: HTTPBasicAuth, card: dict) -> dict:
    url = url_at(f"cards/{card['id']}")
    # TODO I dont like this, how to control what's passed what not?
    # pydantic Model stuff is good for validation, but we probably still need to control what goes thru?
    # because in listing, a card has an id, when updating, the card id comes thru the url ...
    # so we cannot really make the Card Model the only thing, maybe to model_dump(include=...) explicitely?
    card.pop("id")
    response = requests.post(url, json=card, auth=auth)
    assert response.status_code == 200, response.text
    return response.json()


def update_card(
    auth: HTTPBasicAuth, card: Card, attachments: Sequence[Attachment]
) -> Card:
    for attachment in attachments:
        # NOTE depending on changes, we might end up with unreferenced images for a card on the server
        raw_update_attachment(auth, card.id, attachment)
    return Card(**raw_update_card(auth, body_from_model(card)))


def delete_card(auth: HTTPBasicAuth, card_id: str):
    url = url_at(f"cards/{card_id}")
    response = requests.delete(url, auth=auth)
    assert response.status_code == 200, response.text


def auth_from_token(token: str) -> HTTPBasicAuth:
    return HTTPBasicAuth(token, "")
