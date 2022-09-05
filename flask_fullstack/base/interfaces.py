from __future__ import annotations

from typing import TypeVar

t = TypeVar("t", bound="Identifiable")
v = TypeVar("v")


class Identifiable:
    """
    An interface to mark database classes that have an id and can be identified by it.

    Used in :ref:`.Namespace.database_searcher`
    """

    not_found_text: str = ""
    """ Customizable error message to be used for missing ids """

    def __init__(self, **kwargs):
        pass

    @classmethod
    def find_by_id(cls: type[t], entry_id: int) -> t | None:
        raise NotImplementedError


class UserRole:
    """
    An interface to mark database classes as user roles, that can be used for authorization.

    Used in :ref:`.Namespace.jwt_authorizer`
    """

    unauthorized_error: tuple[int | str, str] = (403, "Permission denied")

    def __init__(self, **kwargs):
        pass

    @classmethod
    def find_by_identity(cls: type[t], identity: v) -> t | None:
        raise NotImplementedError

    def get_identity(self) -> v:
        raise NotImplementedError
