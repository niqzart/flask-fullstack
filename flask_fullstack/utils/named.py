from __future__ import annotations


class Nameable:
    name: str = None


class NamedPropertiesMeta(type):  # TODO ability to override names
    def __init__(cls, name: str, bases: tuple[type, ...], namespace: dict[str, ...]):
        qual_name = namespace["__qualname__"]
        for item_name, value in namespace.items():
            if isinstance(value, type) and issubclass(value, Nameable):
                value.name = f"{qual_name}.{item_name}"
        super().__init__(name, bases, namespace)


class NamedProperties(metaclass=NamedPropertiesMeta):
    pass
