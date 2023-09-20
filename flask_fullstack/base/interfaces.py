from __future__ import annotations

from typing import Self, TypeVar

t = TypeVar("t", bound="Identifiable")
v = TypeVar("v")


class Identifiable:
    """
    An interface to mark database classes that have an id and can be identified by it.

    Used in :ref:`.DatabaseSearcherMixin.database_searcher`
    """

    not_found_text: str = ""

    def __init__(self, **kwargs):
        pass

    @classmethod
    def find_by_id(cls, entry_id: int) -> Self | None:
        raise NotImplementedError


class UserRole:
    """
    An interface to mark database classes as user roles, that can be used for authorization.

    Used in :ref:`.JWTAuthorizerMixin.jwt_authorizer`
    """

    unauthorized_error: tuple[int | str, str] = 403, "Permission denied"

    def __init__(self, **kwargs):
        pass

    @classmethod
    def find_by_identity(cls, identity: v) -> Self | None:
        raise NotImplementedError

    def get_identity(self) -> v:
        raise NotImplementedError
