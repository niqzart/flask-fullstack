from __future__ import annotations

from flask_restx.fields import Raw as RawField
from sqlalchemy import JSON


class JSONWithModel(JSON):
    def __init__(
        self,
        model_name: str,
        model: dict | type[RawField] | RawField,
        as_list: bool = False,
        none_as_null=False,
    ):
        super().__init__(none_as_null)
        self.model_name: str = model_name
        self.model: dict | type[RawField] | RawField = model
        self.as_list: bool = as_list
