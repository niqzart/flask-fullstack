from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


# TODO move to ffs utils (not test-bound)
def kebabify_string(data: str) -> str:
    return data.replace("_", "-")


def _kebabify_key(key: str | T, reverse: bool = False) -> str | T:
    if isinstance(key, str):
        return key.replace("-", "_") if reverse else kebabify_string(key)
    return key


def _kebabify(data: T, reverse: bool) -> T:
    if isinstance(data, list):
        return [_kebabify(entry, reverse) for entry in data]
    if isinstance(data, dict):
        return {
            _kebabify_key(k, reverse): _kebabify(v, reverse) for k, v in data.items()
        }
    return data


def kebabify(data: T) -> T:
    return _kebabify(data, reverse=False)


def dekebabify(data: T) -> T:
    return _kebabify(data, reverse=True)
