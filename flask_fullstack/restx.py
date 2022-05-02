from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Union, Type, Sequence

from flask import jsonify
from flask_jwt_extended import unset_jwt_cookies, set_access_cookies, create_access_token, jwt_required
from flask_restx import Namespace, Model as BaseModel, abort as default_abort
from flask_restx.fields import List as ListField, Boolean as BoolField, Integer as IntegerField, Nested
from flask_restx.marshalling import marshal
from flask_restx.reqparse import RequestParser
from flask_restx.utils import unpack

from .interfaces import UserRole
from .marshals import ResponseDoc, Model
from .mixins import DatabaseSearcherMixin, JWTAuthorizerMixin
from .sqlalchemy import Sessionmaker

Undefined = object()


class RestXNamespace(Namespace, DatabaseSearcherMixin, JWTAuthorizerMixin):
    """
    Expansion of :class:`Namespace`, which adds decorators for methods of :class:`Resource`.

    Methods of this class (used as decorators) allow parsing request parameters,
    modifying responses and automatic updates to the Swagger documentation where possible
    """

    def __init__(self, name: str, *, sessionmaker: Sessionmaker, description: str = None, path: str = None,
                 decorators=None, validate=None, authorizations=None, ordered: bool = False, **kwargs):
        super().__init__(name, description, path, decorators, validate, authorizations, ordered, **kwargs)
        self.sessionmaker = sessionmaker

    def with_begin(self, function):
        return self.sessionmaker.with_begin(function)

    def abort(self, code: int, message: str = None, **kwargs):
        default_abort(code, message, **kwargs)

    def doc_abort(self, error_code: Union[int, str], description: str, *, critical: bool = False):
        return self.response(*ResponseDoc.error_response(error_code, description).get_args())

    def add_authorization(self, response, auth_agent: UserRole, auth_name: str = None) -> None:
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
            if len(jwt) != 0:
                set_access_cookies(response, create_access_token(identity=jwt))

    def adds_authorization(self, auth_name: str = None):
        def adds_authorization_wrapper(function):
            @wraps(function)
            @jwt_required(optional=True)
            def adds_authorization_inner(*args, **kwargs):
                response, result, headers = unpack(function(*args, **kwargs))
                if isinstance(result, UserRole):
                    response = jsonify(response)
                    self.add_authorization(response, result, auth_name)
                    return response, 200, headers
                return response, result, headers

            return adds_authorization_inner

        return adds_authorization_wrapper

    def removes_authorization(self, auth_name: str = None):
        def removes_authorization_wrapper(function):
            @wraps(function)
            @jwt_required(optional=True)
            def removes_authorization_inner(*args, **kwargs):
                response, code, headers = unpack(function(*args, **kwargs))
                response = jsonify(response)
                self.remove_authorization(response, auth_name)
                return response, code, headers

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
                    kwargs.update({args.name: Undefined for args in parser.args if args.name not in kwargs.keys()})
                return function(*args, **kwargs)

            return argument_inner

        return argument_wrapper

    def doc_file_param(self, field_name: str):  # redo...
        def doc_file_param_wrapper(function):
            return self.doc(**{
                "params": {field_name: {"in": "formData", "type": "file"}},
                "consumes": "multipart/form-data"
            })(function)

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

    def marshal_with(self, fields: BaseModel | Type[Model], as_list=False, *args, **kwargs):
        result = super().marshal_with

        if isinstance(fields, type) and issubclass(fields, Model):
            model = self.models.get(fields.name, None) or self.model(model=fields)

            def marshal_with_wrapper(function: Callable) -> Callable[..., Model]:
                @wraps(function)
                @result(model, as_list, *args, **kwargs)
                def marshal_with_inner(*args, **kwargs):
                    if as_list:
                        return [fields.convert(d) for d in function(*args, **kwargs)]
                    return fields.convert(function(*args, **kwargs), **kwargs)

                return marshal_with_inner

            return marshal_with_wrapper

        return result(fields, as_list, *args, **kwargs)

    def marshal(self, data, fields: Type[Model] | ..., *args, **kwargs):
        if isinstance(fields, type) and issubclass(fields, Model):
            if isinstance(data, Sequence):
                data = [fields.convert(d) for d in data]
            else:
                data = fields.convert(data)
            fields = self.models.get(fields.name, None) or self.model(model=fields)
        return marshal(data, fields, *args, **kwargs)

    def lister(self, per_request: int, marshal_model: BaseModel | Type[Model], skip_none: bool = True,
               count_all: Callable[..., int] | None = None, provided_total: bool = False):
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
        if isinstance(marshal_model, type) and issubclass(marshal_model, Model):
            name = marshal_model.name
            model = self.models.get(name, None) or self.model(model=marshal_model)
        else:
            name = marshal_model.name
            model = marshal_model

        response = {"results": ListField(Nested(model), max_items=per_request), "has-next": BoolField}
        if count_all is not None or provided_total:
            response["total"] = IntegerField
        response = BaseModel(f"List" + name, response)
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
                    result_list = [marshal_model.convert(result, **kwargs) for result in result_list]
                result = {"results": marshal(result_list, model, skip_none=skip_none), "has-next": has_next}
                if count_all is not None:
                    result["total"] = count_all(*args, **kwargs)
                if provided_total:
                    result["total"] = total
                return result

            return lister_inner

        return lister_wrapper

    def model(self, name: str = None, model=None, **kwargs):
        # TODO recursive registration
        if isinstance(model, type) and issubclass(model, Model):
            if model.name is None:
                model.name = name or model.__qualname__
            return super().model(name or model.name, model.model(), **kwargs)
        return super().model(name, model, **kwargs)
