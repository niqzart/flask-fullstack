from __future__ import annotations

from enum import Enum
from typing import Union


@property
def NotImplementedField(_):
    raise NotImplementedError


class TypeEnum(Enum):
    @classmethod
    def from_string(cls, string: str) -> Union[TypeEnum, None]:
        return cls.__members__.get(string.upper().replace("-", "_"), None)  # TODO NonePointer!!!

    @classmethod
    def get_all_field_names(cls) -> list[str]:
        return [member.lower().replace("_", "-") for member in cls.__members__]

    @classmethod
    def form_whens(cls) -> list[tuple[str, int]]:
        return [(name, value.value) for name, value in cls.__members__.items()]  # TODO IntEnum needed

    def to_string(self) -> str:
        return self.name.lower().replace("_", "-")


def get_or_pop(dictionary: dict, key, keep: bool = False):
    return dictionary[key] if keep else dictionary.pop(key)


def dict_equal(dict1: dict, dict2: dict, *keys) -> bool:
    dict1 = {key: dict1.get(key, None) for key in keys}
    dict2 = {key: dict2.get(key, None) for key in keys}
    return dict1 == dict2


class Nameable:
    name: str = None


class NamedPropertiesMeta(type):
    def __init__(cls, name: str, bases: tuple[type, ...], namespace: dict[str, ...]):
        for name, value in namespace.items():
            if isinstance(value, type) and issubclass(value, Nameable):  # TODO ability to override names
                value.name = namespace["__qualname__"] + "." + name
        super().__init__(name, bases, namespace)


class NamedProperties(metaclass=NamedPropertiesMeta):
    pass
