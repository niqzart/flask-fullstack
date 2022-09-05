from __future__ import annotations


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
