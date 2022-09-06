from __future__ import annotations

from enum import Enum

from .dicts import remove_none


@property
def NotImplementedField(_):
    raise NotImplementedError


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


def render_packed(
    data: dict | str | int | None = None,
    code: int | None = None,
    message: str | None = None,
) -> dict:
    return remove_none({"code": code, "message": message, "data": data})
