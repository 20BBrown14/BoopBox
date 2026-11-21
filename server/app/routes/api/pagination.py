"""Offset pagination shared by the list endpoints.

Each endpoint subclasses `Page` under its own name (`class UserPage(Page[UserOut])`)
so the OpenAPI schema, and the generated frontend types, get a readable name.
"""

from dataclasses import dataclass

from fastapi import Query
from pydantic import BaseModel

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@dataclass(frozen=True)
class PageParams:
    limit: int
    offset: int


def page_params(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
