from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Type, Union

from pydantic.v1 import BaseModel, Field, ValidationError, create_model
from pydantic.v1.fields import FieldInfo

# TODO redo with | for python 3.10+
LiteralType = Union[int, str, bool, float, Enum]
TypeChecker = Union[
    None, type, dict, list, set, Type[LiteralType], BaseModel, LiteralType
]
TypeType = Union[type, BaseModel]
FieldType = tuple[TypeType, FieldInfo]


def contained_list(expected: list[TypeChecker]) -> type:
    class ContainedList(list):
        @classmethod
        def validate(cls, value: list) -> list:
            if not isinstance(value, list):
                raise TypeError("list required")
            if len(expected) != len(value):
                raise ValueError("length doesn't match")
            for i, (real_value, expected_value) in enumerate(zip(value, expected)):
                check_contains(real_value, expected_value, field_name=str(i))
            return value

        @classmethod
        def __get_validators__(cls):
            yield cls.validate

    return ContainedList


class Something:
    @classmethod
    def validate(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("something required, not None")
        return value

    @classmethod
    def __get_validators__(cls):
        yield cls.validate


def convert_to_type(source: TypeChecker) -> TypeType:
    if source is None:
        return type(None)
    if source is ...:
        return Something
    if source is Any:
        return Any
    if isinstance(source, type):
        return source
    if isinstance(source, dict):
        fields: dict[str, FieldType] = {
            key: convert_to_field(value) for key, value in source.items()
        }
        return create_model("Model", **fields)
    if isinstance(source, list):
        return contained_list(source)
    if isinstance(source, BaseModel):
        return source
    return Literal[source]  # type: ignore


def convert_to_field(source: TypeChecker) -> FieldType:
    if source is None:
        return type(None), Field(default=None)
    return convert_to_type(source), Field()


def check_contains(real: ..., expected: TypeChecker, field_name: str) -> None:
    create_model(
        "Model",
        **{field_name: convert_to_field(expected)},
    ).parse_obj({field_name: real})


def assert_contains(real: ..., expected: TypeChecker) -> None:
    try:
        create_model("Model", __root__=convert_to_field(expected)).parse_obj(real)
    except ValidationError as e:
        raise AssertionError(str(e))
