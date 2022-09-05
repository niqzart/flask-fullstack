from __future__ import annotations

from typing import Type

from flask_restx.fields import Raw as RawField
from sqlalchemy import JSON


class JSONWithModel(JSON):
    def __init__(self, model_name: str, model: dict | Type[RawField] | RawField,
                 as_list: bool = False, none_as_null=False):
        super().__init__(none_as_null)
        self.model_name: str = model_name
        self.model: dict | Type[RawField] | RawField = model
        self.as_list: bool = as_list


class JSONWithSchema(JSON):
    def __init__(self, schema_type: str, schema_format=None, schema_example=None, none_as_null=False):
        super().__init__(none_as_null)
        self.schema_type = schema_type
        self.schema_format = schema_format
        self.schema_example = schema_example
