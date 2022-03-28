from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Union

from flask_restx import Namespace, Model as BaseModel, abort as default_abort
from flask_restx.fields import List as ListField, Boolean as BoolField, Nested
from flask_restx.marshalling import marshal
from flask_restx.reqparse import RequestParser

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
        return self.response(*ResponseDoc.error_response("404 ", description).get_args())

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

    def marshal_with(self, fields: BaseModel | Model, **kwargs):
        result = super().marshal_with(fields, **kwargs)
        if isinstance(fields, Model):
            def marshal_with_wrapper(function: Callable) -> Callable[..., Model]:
                @wraps(function)
                @result
                def marshal_with_inner(*args, **kwargs):
                    return fields.convert(function(*args, **kwargs), **kwargs)

                return marshal_with_inner

            return marshal_with_wrapper

        return result

    def lister(self, per_request: int, marshal_model: BaseModel, skip_none: bool = True):
        """
        - Used for organising pagination.
        - Uses `counter` form incoming arguments for the decorated function and `per_request` argument
          to define start and finish indexes, passed as keyword arguments to the decorated function.
        - Marshals the return of the decorated function as a list with `marshal_model`.
        - Adds information on the response to documentation automatically.

        :param per_request:
        :param marshal_model:
        :param skip_none:
        :return:
        """
        response = ResponseDoc(200, f"Max size of results: {per_request}", BaseModel(f"List" + marshal_model.name, {
            "results": ListField(Nested(marshal_model), max_items=per_request), "has-next": BoolField}))

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

                if has_next := len(result_list) > per_request:
                    result_list.pop()

                return {"results": marshal(result_list, marshal_model, skip_none=skip_none), "has-next": has_next}

            return lister_inner

        return lister_wrapper

    def model(self, name: str = None, model=None, **kwargs):
        if isinstance(model, Model):
            return super().model(name or Model.__name__, model.model(), **kwargs)
        return super().model(name, model, **kwargs)
