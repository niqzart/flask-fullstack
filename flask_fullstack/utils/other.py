from __future__ import annotations

from enum import Enum

from .dicts import remove_none


@property
def NotImplementedField(_):
    raise NotImplementedError


class TypeEnumInput:
    def __init__(self, enum: type[TypeEnum]):
        self.enum = enum

    def __call__(self, value: str):
        return self.enum.validate(value)

    @property
    def __schema__(self) -> dict:
        return {
            "type": "string",
            "enum": self.enum.get_all_field_names(),
        }


class TypeEnum(Enum):
    @classmethod
    def from_string(cls, string: str) -> TypeEnum | None:  # TODO NonePointer!!!
        return cls.__members__.get(string.upper().replace("-", "_"), None)

    @classmethod
    def get_all_field_names(cls) -> list[str]:
        return [member.lower().replace("_", "-") for member in cls.__members__]

    @classmethod
    def form_whens(cls) -> list[tuple[str, int]]:  # TODO IntEnum needed
        return [(name, value.value) for name, value in cls.__members__.items()]

    def to_string(self) -> str:
        return self.name.lower().replace("_", "-")

    @classmethod
    def validate(cls, string: str):
        result = cls.from_string(string)
        if result is None:
            raise ValueError(f"{string} is not a valid {cls.__name__}")
        return result

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def as_input(cls):
        return TypeEnumInput(cls)


def render_packed(
    data: dict | list | str | int | None = None,
    code: int | None = None,
    message: str | None = None,
) -> dict:
    return remove_none({"code": code, "message": message, "data": data})
