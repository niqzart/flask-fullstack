from __future__ import annotations

from abc import ABCMeta
from functools import wraps
from typing import Type, Union

from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request, get_jwt

from .interfaces import Identifiable, UserRole
from .utils import get_or_pop


class AbstractAbortMixin:
    def abort(self, error_code: Union[int, str], description: str, *, critical: bool = False, **kwargs):
        raise NotImplementedError

    def doc_abort(self, error_code: Union[int, str], description: str, *, critical: bool = False):
        raise NotImplementedError

    def doc_aborts(self, *responses: Union[tuple[Union[int, str], str], tuple[Union[int, str], str, bool]]):
        def doc_aborts_wrapper(function):
            for response in responses:
                function = self.doc_abort(
                    response[0], response[1], critical=response[2] if len(response) == 3 else False)(function)
            return function

        return doc_aborts_wrapper


class RawDatabaseSearcherMixin(AbstractAbortMixin, metaclass=ABCMeta):
    def with_begin(self, function):
        raise NotImplementedError

    # deprecated
    def _database_searcher(self, identifiable: Type[Identifiable], check_only: bool, no_id: bool,
                           use_session: bool, error_code: int, callback, args, kwargs, *,
                           input_field_name: Union[str, None] = None, result_field_name: Union[str, None] = None):
        if input_field_name is None:
            input_field_name = identifiable.__name__.lower() + "_id"
        if result_field_name is None:
            result_field_name = identifiable.__name__.lower()
        session = get_or_pop(kwargs, "session", use_session)
        target_id: int = get_or_pop(kwargs, input_field_name, check_only and not no_id)
        if (result := identifiable.find_by_id(session, target_id)) is None:
            self.abort(error_code, identifiable.not_found_text)
        else:
            if not check_only:
                kwargs[result_field_name] = result
            return callback(*args, **kwargs)


class DatabaseSearcherMixin(RawDatabaseSearcherMixin, metaclass=ABCMeta):
    def database_searcher(self, identifiable: Type[Identifiable], *, input_field_name: str = None,
                          result_field_name: str = None, check_only: bool = False, use_session: bool = False,
                          error_code: int | str = " 404"):
        """
        - Uses incoming id argument to find something :class:`Identifiable` in the database.
        - If the entity wasn't found, will return a 404 response, which is documented automatically.
        - Can pass (entity's id or entity) and session objects to the decorated function.

        :param identifiable: identifiable to search for
        :param input_field_name: overrides default name of a parameter to search by
        [default: identifiable.__name__.lower() + "_id"]
        :param result_field_name: overrides default name of found object [default: identifiable.__name__.lower()]
        :param check_only: (default: False) if True, checks if entity exists and passes id to the decorated function
        :param use_session: (default: False) whether to pass the session to the decorated function
        :param error_code: (default: " 404") an override for the documentation code for a not-found error
        """
        if input_field_name is None:
            input_field_name = identifiable.__name__.lower() + "_id"
        if result_field_name is None:
            result_field_name = identifiable.__name__.lower()

        int_error_code: int = int(error_code)  # TODO redo doc_abort to handle this automagically

        def searcher_wrapper(function):
            @self.doc_abort(error_code, identifiable.not_found_text, critical=True)
            @wraps(function)
            @self.with_begin
            def searcher_inner(*args, **kwargs):
                session = get_or_pop(kwargs, "session", use_session)
                target_id: int = get_or_pop(kwargs, input_field_name, check_only)

                if (result := identifiable.find_by_id(session, target_id)) is None:
                    self.abort(int_error_code, identifiable.not_found_text)

                if not check_only:
                    kwargs[result_field_name] = result
                return function(*args, **kwargs)

            return searcher_inner

        return searcher_wrapper


class JWTAuthorizerMixin(RawDatabaseSearcherMixin, metaclass=ABCMeta):
    auth_errors: list[tuple[Union[int, str], str, bool]] = [
        ("401 ", "JWTError", True),
        ("422 ", "InvalidJWT", True)
    ]

    def _get_identity(self) -> dict | None:
        try:
            verify_jwt_in_request(optional=True)
            jwt: dict = get_jwt_identity()
        except Exception:
            return None

        if not isinstance(jwt, dict):
            return None
        return jwt

    @staticmethod
    def with_required_jwt(**kwargs):
        return jwt_required(**kwargs)

    @staticmethod
    def with_optional_jwt(**kwargs):
        return jwt_required(optional=True, **kwargs)

    def jwt_authorizer(self, role: Type[UserRole], auth_name: str = "", *, result_field_name: str = None,
                       optional: bool = False, check_only: bool = False, use_session: bool = True):
        """
        - Authorizes user by JWT-token.
        - If token is missing or is not processable, falls back on flask-jwt-extended error handlers.
        - If user doesn't exist or doesn't have the role required, sends the corresponding response.
        - All error responses are added to the documentation automatically.
        - Can pass user and session objects to the decorated function.

        :param role: role to expect
        :param auth_name: which identity to use for searching. "" is the default for single-auth setups
        :param optional: (default: False)
        :param check_only: (default: False) if True, user object won't be passed to the decorated function
        :param use_session: (default: True) whether to pass the session to the decorated function
        :param result_field_name: overrides default name of found object [default: role.__name__.lower()]
        """
        auth_errors = self.auth_errors.copy()
        auth_errors.append(role.unauthorized_error + (True,))

        if result_field_name is None:
            result_field_name = role.__name__.lower()

        def authorizer_wrapper(function):
            @self.doc_aborts(*auth_errors)
            @wraps(function)
            @jwt_required(optional=optional)
            @self.with_begin
            def authorizer_inner(*args, **kwargs):
                if (t := self._get_identity()) is None or (identity := t.get(auth_name, None)) is None:
                    if optional:
                        kwargs[role.__name__.lower()] = None
                        return function(*args, **kwargs)
                    self.abort(*role.unauthorized_error)

                session = get_or_pop(kwargs, "session", use_session)
                if (result := role.find_by_identity(session, identity)) is None:
                    self.abort(*role.unauthorized_error)

                if not check_only:
                    kwargs[result_field_name] = result
                return function(*args, **kwargs)

            return authorizer_inner

        return authorizer_wrapper
