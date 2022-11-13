from __future__ import annotations

from flask_restx import Model
from flask_restx.fields import Raw


def rename_model_ref_once(key: str, value: str | dict) -> str | dict:
    if key == "$ref":
        return value.replace("#/definitions", "#/components/messages") + "/payload"
    elif isinstance(value, dict):
        return rename_model_refs(value)
    return value


def rename_model_refs(dct: dict) -> dict:
    return {k: rename_model_ref_once(k, v) for k, v in dct.items()}


def restx_model_to_schema(name: str, model: dict[str, type[Raw] | Raw]):
    return rename_model_refs(Model(name, model).__schema__)


def restx_model_to_message(name: str, model: dict[str, type[Raw] | Raw]):
    return {"payload": restx_model_to_schema(name, model)}
