from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TypeVar, Type

from sqlalchemy import JSON, MetaData
from sqlalchemy.engine import Result, ScalarResult
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.sql import Select


class Sessionmaker(sessionmaker):
    def with_begin(self, function):
        """ Wraps the function with Session.begin() and passes session object to the decorated function """

        @wraps(function)
        def with_begin_inner(*args, **kwargs):
            if "session" in kwargs.keys():
                return function(*args, **kwargs)
            with self.begin() as session:
                kwargs["session"] = session
                return function(*args, **kwargs)

        return with_begin_inner

    def with_autocommit(self, function):
        """ Wraps the function with Session.begin() for automatic commits after the decorated function """

        @wraps(function)
        def with_autocommit_inner(*args, **kwargs):
            with self.begin() as _:
                return function(*args, **kwargs)

        return with_autocommit_inner

    def execute(self, function: Callable[..., Select]) -> Callable[..., Result]:
        """ """

        @wraps(function)
        @self.with_begin
        def execute_inner(*args, **kwargs):
            session = kwargs["session"]
            return session.execute(function(*args, **kwargs))

        return execute_inner

    def extract_scalars(self, function: Callable[..., Result]) -> Callable[..., ScalarResult]:
        @wraps(function)
        def extract_scalars(*args, **kwargs):
            return function(*args, **kwargs).scalars()

        return extract_scalars

    def extract_first(self, function: Callable[..., Result]) -> Callable[..., ...]:
        @wraps(function)
        def extract_first_inner(*args, **kwargs):
            return function(*args, **kwargs).first()

        return extract_first_inner

    def extract_all(self, function: Callable[..., Result]) -> Callable[..., ...]:
        @wraps(function)
        def extract_all_inner(*args, **kwargs):
            return function(*args, **kwargs).all()

        return extract_all_inner

    def select_paginated(self, function: Callable[..., Select]) -> Callable[..., ...]:
        @wraps(function)
        def select_paginated_inner(*args, **kwargs):
            return function(*args, **kwargs).offset(kwargs["offset"]).limit(kwargs["limit"])

        return select_paginated_inner

    def select_first(self, function: Callable[..., Select]) -> Callable[..., ...]:
        @wraps(function)
        @self.extract_first
        @self.extract_scalars
        @self.execute
        def select_first_inner(*args, **kwargs):
            return function(*args, **kwargs)

        return select_first_inner

    def get_all(self, function: Callable[..., Select]) -> Callable[..., list[...]]:
        @wraps(function)
        @self.extract_all
        @self.extract_scalars
        @self.execute
        def get_all_inner(*args, **kwargs):
            return function(*args, **kwargs)

        return get_all_inner

    def get_paginated(self, function: Callable[..., Select]) -> Callable[..., list[...]]:
        @wraps(function)
        @self.extract_all
        @self.extract_scalars
        @self.execute
        @self.select_paginated
        def get_paginated_inner(*args, **kwargs):
            return function(*args, **kwargs)

        return get_paginated_inner


class JSONWithModel(JSON):
    def __init__(self, model_name: str, model: dict, as_list: bool = False, none_as_null=False):
        super().__init__(none_as_null)
        self.model_name: str = model_name
        self.model: dict = model
        self.as_list: bool = as_list


class JSONWithSchema(JSON):
    def __init__(self, schema_type: str, schema_format=None, schema_example=None, none_as_null=False):
        super().__init__(none_as_null)
        self.schema_type = schema_type
        self.schema_format = schema_format
        self.schema_example = schema_example


def create_base(meta: MetaData) -> Type:
    t = TypeVar("t", bound="ModBase")

    class ModBase(declarative_base(metadata=meta)):
        __abstract__ = True

        @classmethod
        def create(cls: Type[t], session: Session, **kwargs) -> t:
            entry = cls(**kwargs)
            session.add(entry)
            session.flush()
            return entry

        # TODO find_by_... with reflection

        def delete(self, session: Session) -> None:
            session.delete(session)
            session.flush()

    return ModBase
