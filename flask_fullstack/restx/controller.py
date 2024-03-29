from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import wraps
from typing import Any

from flask import jsonify
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
)
from flask_restx import Model as BaseModel, Namespace, abort as default_abort
from flask_restx.fields import (
    Boolean as BoolField,
    Integer as IntegerField,
    List as ListField,
    Nested,
)
from flask_restx.marshalling import marshal
from flask_restx.reqparse import RequestParser
from flask_restx.utils import merge, unpack
from pydantic import BaseModel as BaseModelV2

from .marshals import Model, ResponseDoc, v2_model_to_ffs
from ..base import DatabaseSearcherMixin, JWTAuthorizerMixin, UserRole

Undefined = object()


class ResourceController(Namespace, DatabaseSearcherMixin, JWTAuthorizerMixin):
    """
    Expansion of :class:`Namespace`, which adds decorators for methods of :class:`Resource`.

    Methods of this class (used as decorators) allow parsing request parameters,
    modifying responses and automatic updates to the Swagger documentation where possible
    """

    def __init__(
        self,
        name: str,
        *,
        description: str = None,
        path: str = None,
        decorators=None,
        validate=None,
        authorizations=None,
        ordered: bool = False,
        **kwargs,
    ):
        super().__init__(
            name,
            description,
            path,
            decorators,
            validate,
            authorizations,
            ordered,
            **kwargs,
        )

    def abort(self, code: int, message: str = None, **kwargs):
        default_abort(code, message, **kwargs)

    def doc_abort(
        self,
        error_code: int | str,
        description: str,
    ):
        response = ResponseDoc.error_response(error_code, description)
        return self.response(*response.get_args())

    def add_authorization(
        self,
        response,
        auth_agent: UserRole,
        auth_name: str = None,
    ) -> None:
        jwt = self._get_identity()
        if jwt is None:
            jwt = {}
        jwt[auth_name or ""] = auth_agent.get_identity()
        set_access_cookies(response, create_access_token(identity=jwt))

    def remove_authorization(self, response, auth_name: str = None) -> None:
        jwt = self._get_identity()
        unset_jwt_cookies(response)
        if jwt is not None:
            jwt.pop(auth_name or "")
            if jwt:
                set_access_cookies(response, create_access_token(identity=jwt))

    def adds_authorization(self, auth_name: str = None):
        def adds_authorization_wrapper(function):
            @wraps(function)
            def adds_authorization_inner(*args, **kwargs):
                response, result, headers = unpack(function(*args, **kwargs))
                if isinstance(result, UserRole):  # TODO passthrough for headers
                    response = jsonify(response)
                    self.add_authorization(response, result, auth_name)
                    return response
                return response, result, headers

            return adds_authorization_inner

        return adds_authorization_wrapper

    def removes_authorization(self, auth_name: str = None):
        def removes_authorization_wrapper(function):
            @wraps(function)
            @jwt_required()
            def removes_authorization_inner(*args, **kwargs):
                response, code, headers = unpack(function(*args, **kwargs))
                response = jsonify(response)  # TODO passthrough for headers & code
                self.remove_authorization(response, auth_name)
                return response

            return removes_authorization_inner

        return removes_authorization_wrapper

    def argument_parser(self, parser: RequestParser, use_undefined: bool = False):
        """
        - Parses request parameters and adds them to kwargs used to call the decorated function.
        - Automatically updates endpoint's parameters with arguments from the parser.
        """

        def argument_wrapper(function):
            @self.expect(parser)
            @wraps(function)
            def argument_inner(*args, **kwargs):
                kwargs.update(parser.parse_args())
                if use_undefined:
                    kwargs.update(
                        {
                            args.dest or args.name: Undefined
                            for args in parser.args
                            if (args.dest or args.name) not in kwargs.keys()
                        }
                    )
                return function(*args, **kwargs)

            return argument_inner

        return argument_wrapper

    def doc_file_param(self, field_name: str):  # redo...
        def doc_file_param_wrapper(function):
            return self.doc(
                params={field_name: {"in": "formData", "type": "file"}},
                consumes="multipart/form-data",
            )(function)

        return doc_file_param_wrapper

    def doc_responses(self, *responses: ResponseDoc):
        """
        Adds responses to the documentation. **Affects docs only!**

        :param responses: all responses to document. Models inside are registered automatically.
        """

        def doc_responses_wrapper(function):
            for response in responses:
                response.register_model(self)
                function = self.response(*response.get_args())(function)
            return function

        return doc_responses_wrapper

    def _marshal_result(self, result, fields: type[Model], as_list: bool, **context):
        if as_list:
            return [fields.convert(d, **context) for d in result]
        return fields.convert(result, **context)

    def marshal_with(
        self,
        fields: BaseModel | type[Model] | type[BaseModelV2],
        as_list=False,
        skip_none=True,
        *args,
        **kwargs,
    ):
        result = super().marshal_with

        if self.is_registrable(fields):
            if issubclass(fields, BaseModelV2):
                fields = v2_model_to_ffs(fields)
            model = self.models.get(fields.name, None) or self.model(model=fields)

            def marshal_with_wrapper(function: Callable) -> Callable[..., Model]:
                @wraps(function)
                @result(model, as_list, *args, skip_none=skip_none, **kwargs)
                def marshal_with_inner(*args, **kwargs):
                    result = function(*args, **kwargs)
                    if isinstance(result, tuple):
                        result, code, headers = unpack(result)
                        return (
                            self._marshal_result(result, fields, as_list, **kwargs),
                            code,
                            headers,
                        )
                    return self._marshal_result(result, fields, as_list, **kwargs)

                return marshal_with_inner

            return marshal_with_wrapper

        return result(fields, as_list, *args, skip_none=skip_none, **kwargs)

    def marshal(self, data, fields: type[Model] | ..., context=None, *args, **kwargs):
        if self.is_registrable(fields):
            if issubclass(fields, BaseModelV2):
                fields = v2_model_to_ffs(fields)
            if isinstance(data, Sequence):
                data = [fields.convert(d, **context or {}) for d in data]
            else:
                data = fields.convert(data, **context or {})
            fields = self.models.get(fields.name, None) or self.model(model=fields)
        return marshal(data, fields, *args, **kwargs)

    def marshal_with_authorization(
        self,
        fields: BaseModel | type[Model] | type[BaseModelV2],
        as_list: bool = False,
        auth_name: str = None,
        **kwargs,
    ):
        name = getattr(fields, "name", fields.__name__)
        model = self.models.get(name, None) or self.model(model=fields)

        def marshal_with_authorization_wrapper(function):
            doc = {
                "responses": {
                    "200": (None, [model], kwargs) if as_list else (None, model, kwargs)
                },
                "__mask__": kwargs.get(
                    "mask", True
                ),  # Mask values can't be determined outside app context
            }
            function.__apidoc__ = merge(getattr(function, "__apidoc__", {}), doc)

            @wraps(function)
            def marshal_with_authorization_inner(*args, **kwargs):
                response, result, headers = unpack(function(*args, **kwargs))
                if isinstance(result, UserRole):  # TODO passthrough for headers
                    response = jsonify(
                        self.marshal(response, fields, skip_none=True, context=kwargs)
                    )
                    self.add_authorization(response, result, auth_name)
                    return response
                return response, result, headers

            return marshal_with_authorization_inner

        return marshal_with_authorization_wrapper

    def lister(
        self,
        per_request: int,
        marshal_model: BaseModel | type[Model] | type[BaseModelV2],
        skip_none: bool = True,
        count_all: Callable[..., int] | None = None,
        provided_total: bool = False,
    ):
        """
        - Used for organising pagination.
        - Uses `counter` form incoming arguments for the decorated function and `per_request` argument
          to define start and finish indexes, passed as keyword arguments to the decorated function.
        - Marshals the return of the decorated function as a list with `marshal_model`.
        - Adds information on the response to documentation automatically.

        :param per_request:
        :param marshal_model:
        :param skip_none:
        :param count_all:
        :param provided_total:
        :return:
        """
        if self.is_registrable(marshal_model):
            name = getattr(marshal_model, "name", marshal_model.__name__)
            model = self.models.get(name, None) or self.model(model=marshal_model)
        else:
            name = marshal_model.name
            model = marshal_model

        response = {
            "results": ListField(Nested(model), max_items=per_request),
            "has-next": BoolField,
        }
        if count_all is not None or provided_total:
            response["total"] = IntegerField
        response = BaseModel(f"List{name}", response)
        response = ResponseDoc(200, f"Max size of results: {per_request}", response)

        def lister_wrapper(function):
            @self.doc_responses(response)
            @wraps(function)
            def lister_inner(*args, **kwargs):
                offset: int = kwargs.pop("offset", None)
                counter: int = kwargs.pop("counter", None)
                if offset is None:
                    if counter is None:
                        self.abort(400, "Neither counter nor offset are provided")
                    offset = counter * per_request

                kwargs["start"] = offset
                kwargs["finish"] = offset + per_request + 1
                result_list = function(*args, **kwargs)
                if provided_total:
                    total = result_list[1]
                    result_list = result_list[0]

                if has_next := len(result_list) > per_request:
                    result_list.pop()

                if isinstance(marshal_model, type) and issubclass(marshal_model, Model):
                    result_list = [
                        marshal_model.convert(result, **kwargs)
                        for result in result_list
                    ]
                result = {
                    "results": marshal(result_list, model, skip_none=skip_none),
                    "has-next": has_next,
                }
                if count_all is not None:
                    result["total"] = count_all(*args, **kwargs)
                if provided_total:
                    result["total"] = total
                return result

            return lister_inner

        return lister_wrapper

    def is_registrable(self, model: Any) -> bool:
        return isinstance(model, type) and (
            issubclass(model, Model) or issubclass(model, BaseModelV2)
        )

    def model(self, name: str = None, model=None, **kwargs):
        # TODO recursive registration
        if self.is_registrable(model):
            if issubclass(model, BaseModelV2):
                model = v2_model_to_ffs(model)
            if model.name is None:
                model.name = name or model.__qualname__
            return super().model(name or model.name, model.model(), **kwargs)
        return super().model(name, model, **kwargs)
