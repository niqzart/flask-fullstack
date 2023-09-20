from __future__ import annotations

from typing import Any, TypeVar


def get_or_pop(dictionary: dict, key, keep: bool = False):
    return dictionary[key] if keep else dictionary.pop(key)


K = TypeVar("K")
Undefined = object()


def dict_cut(source: dict[K, Any], *keys: K, default: Any = Undefined) -> dict[K, Any]:
    if default is Undefined:
        return {key: source[key] for key in keys}
    return {key: source.get(key, default) for key in keys}


def dict_reduce(source: dict[K, Any], *keys: K) -> dict[K, Any]:
    return {key: value for key, value in source.items() if key not in keys}


def dict_rekey(source: dict[K, Any], **mapping: K) -> dict[K, Any]:
    return {mapping.get(key, key): value for key, value in source.items()}


def dict_equal(dict1: dict, dict2: dict, *keys) -> bool:
    dict1 = {key: dict1.get(key) for key in keys}
    dict2 = {key: dict2.get(key) for key in keys}
    return dict1 == dict2


def remove_none(data: dict, **kwargs):
    return {
        key: value for key, value in dict(data, **kwargs).items() if value is not None
    }
