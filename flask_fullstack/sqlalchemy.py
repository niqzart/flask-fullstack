from __future__ import annotations

from functools import wraps
from typing import TypeVar, Type

from sqlalchemy import JSON, MetaData, select
from sqlalchemy.engine import Row
from sqlalchemy.orm import sessionmaker, declarative_base, Session as _Session
from sqlalchemy.sql import Select


class Session(_Session):
    def get_first(self, stmt: Select) -> object | None:
        return self.execute(stmt).scalars().first()

    def get_first_row(self, stmt: Select) -> Row:
        return self.execute(stmt).first()

    def get_all(self, stmt: Select) -> list[object]:
        return self.execute(stmt).scalars().all()

    def get_all_rows(self, stmt: Select) -> list[Row]:
        return self.execute(stmt).all()

    def get_paginated(self, stmt: Select, offset: int, limit: int) -> list[object]:
        return self.get_all(stmt.offset(offset).limit(limit))

    def get_paginated_rows(self, stmt: Select, offset: int, limit: int) -> list[Row]:
        return self.get_all_rows(stmt.offset(offset).limit(limit))


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


t = TypeVar("t", bound="ModBase")


class ModBase:
    @classmethod
    def create(cls: Type[t], session: Session, **kwargs) -> t:
        entry = cls(**kwargs)
        session.add(entry)
        session.flush()
        return entry

    @classmethod
    def find_first_by_kwargs(cls, session, **kwargs):
        return session.get_first(select(cls).filter_by(**kwargs))

    @classmethod
    def find_first_row_by_kwargs(cls, session, **kwargs):
        return session.get_first_row(select(cls).filter_by(**kwargs))

    @classmethod
    def find_all_by_kwargs(cls, session, **kwargs):
        return session.get_all(select(cls).filter_by(**kwargs))

    @classmethod
    def find_all_rows_by_kwargs(cls, session, **kwargs):
        return session.get_all_rows(select(cls).filter_by(**kwargs))

    # TODO find_by_... with reflection

    def delete(self, session: Session) -> None:
        session.delete(self)
        session.flush()


def create_base(meta: MetaData) -> Type[ModBase]:
    return declarative_base(metadata=meta, cls=ModBase)
