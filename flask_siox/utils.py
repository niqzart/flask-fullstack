from __future__ import annotations

from typing import Sequence, Type

from pydantic import BaseModel


def remove_none(data: dict, **kwargs):
    return {key: value for key, value in dict(data, **kwargs).items() if value is not None}


def render_model(model: Type[BaseModel], data, **kwargs) -> dict:
    if not isinstance(data, model):
        data = model.parse_obj(data)
    return data.dict(**kwargs)


def unpack_params(result: Sequence) -> tuple[dict | None, int | None, str | None]:
    code: int | None = None
    message: str | None = None

    if len(result) == 2:
        data, second = result
        if isinstance(second, int):
            code = second
        elif isinstance(second, str):
            message = second
    elif len(result) == 3:
        data, code, message = result

    if isinstance(data, str) and message is None:
        return None, code, data

    return data, code, message


def render_packed(data: dict | str | int | None = None, code: int | None = None, message: str | None = None) -> dict:
    return remove_none({"code": code, "message": message, "data": data})


def kebabify_model(model: Type[BaseModel]):
    for f_name, field in model.__fields__.items():
        if field.alias == f_name:
            field.alias = field.name.replace("_", "-")
