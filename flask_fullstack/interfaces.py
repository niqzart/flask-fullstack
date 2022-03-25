from __future__ import annotations

from typing import Union, TypeVar, Type

t = TypeVar("t", bound="ModBase")


class Identifiable:
    """
    An interface to mark database classes that have an id and can be identified by it.

    Used in :ref:`.Namespace.database_searcher`
    """

    not_found_text: str = ""
    """ Customizable error message to be used for missing ids """
    primary_keys: str | list[str] = "id"
    """  """

    def __init__(self, **kwargs):
        pass

    @classmethod
    def find_first(cls: Type[t], **kwargs) -> t | None:
        raise NotImplementedError

    @classmethod
    def find_all(cls: Type[t], **kwargs) -> list[t]:
        raise NotImplementedError

    @classmethod
    def find_paginated(cls: Type[t], offset: int, limit: int, **kwargs) -> list[t]:
        raise NotImplementedError


class UserRole(Identifiable):
    """
    An interface to mark database classes as user roles, that can be used for authorization.

    Used in :ref:`.Namespace.jwt_authorizer`
    """

    default_role: Union[UserRole, None] = None

    @classmethod
    def find_first(cls: Type[t], **kwargs) -> t | None:
        raise NotImplementedError

    @classmethod
    def find_all(cls: Type[t], **kwargs) -> list[t]:
        raise NotImplementedError

    @classmethod
    def find_paginated(cls: Type[t], offset: int, limit: int, **kwargs) -> list[t]:
        raise NotImplementedError
