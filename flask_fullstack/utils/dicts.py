from __future__ import annotations


def get_or_pop(dictionary: dict, key, keep: bool = False):
    return dictionary[key] if keep else dictionary.pop(key)


def dict_equal(dict1: dict, dict2: dict, *keys) -> bool:
    dict1 = {key: dict1.get(key, None) for key in keys}
    dict2 = {key: dict2.get(key, None) for key in keys}
    return dict1 == dict2


def remove_none(data: dict, **kwargs):
    return {
        key: value
        for key, value in dict(data, **kwargs).items()
        if value is not None
    }
