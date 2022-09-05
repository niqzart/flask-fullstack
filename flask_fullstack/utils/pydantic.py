from __future__ import annotations

from typing import Type

from pydantic import BaseModel


def render_model(model: Type[BaseModel], data, **kwargs) -> dict:
    if not isinstance(data, model):
        data = model.parse_obj(data)
    return data.dict(**kwargs)


def kebabify_model(model: Type[BaseModel]):
    for f_name, field in model.__fields__.items():
        if field.alias == f_name:
            field.alias = field.name.replace("_", "-")
