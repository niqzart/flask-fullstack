from __future__ import annotations

from typing import Hashable

from flask_restx.reqparse import (
    LOCATIONS,
    PY_TYPES,
    Argument as BaseArgument,
    ParseResult,
    RequestParser as BaseRequestParser,
)


class Argument(BaseArgument):
    @property
    def __schema__(self):
        if self.location == "cookie":
            return None
        param = {"name": self.name, "in": LOCATIONS.get(self.location, "query")}

        if isinstance(self.type, Hashable) and self.type in PY_TYPES:
            base_param = {"type": PY_TYPES[self.type]}
        elif hasattr(self.type, "__apidoc__"):
            base_param = {"type": self.type.__apidoc__["name"]}
            param["in"] = "body"
        elif hasattr(self.type, "__schema__"):
            base_param = self.type.__schema__
        elif self.location == "files":
            base_param = {"type": "file"}
        else:
            base_param = {"type": "string"}

        if self.required:
            param["required"] = True
        if self.help:
            param["description"] = self.help
        if self.default is not None:
            param["default"] = (
                self.default() if callable(self.default) else self.default
            )
        if self.choices:
            param["enum"] = self.choices

        if self.action == "append":
            param["items"] = base_param
            param["type"] = "array"
            param["collectionFormat"] = "multi"
        elif self.action == "split":
            param["items"] = base_param
            param["type"] = "array"
            param["collectionFormat"] = "csv"
        else:
            param.update(base_param)

        return param


class RequestParser(BaseRequestParser):
    default_argument_class: type[BaseArgument] = Argument
    default_result_class: type[ParseResult] = ParseResult

    def __init__(
        self,
        argument_class: type[BaseArgument] = None,
        result_class: type[ParseResult] = None,
        trim: bool = False,
        bundle_errors: bool = False,
    ):
        super().__init__(
            argument_class=argument_class or self.default_argument_class,
            result_class=result_class or self.default_result_class,
            bundle_errors=bundle_errors,
            trim=trim,
        )


counter_parser: RequestParser = RequestParser()
counter_parser.add_argument(
    "counter", type=int, required=False, help="The page number for pagination"
)
counter_parser.add_argument(
    "offset", type=int, required=False, help="The starting entity index"
)

password_parser: RequestParser = RequestParser()
password_parser.add_argument("password", required=True, help="User's password")
