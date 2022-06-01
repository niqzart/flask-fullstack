from __future__ import annotations

from abc import ABCMeta
from dataclasses import dataclass
from datetime import datetime
from json import dumps, loads
from typing import Union, Type

from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restx import Model
from flask_socketio import disconnect, join_room
from pydantic import BaseModel
from socketio.exceptions import ConnectionRefusedError

from .marshals import PydanticModel
from .mixins import DatabaseSearcherMixin, JWTAuthorizerMixin
from .sqlalchemy import Sessionmaker
from .utils import Nameable, TypeEnum
from ..flask_siox import (Namespace as _Namespace, EventGroup as _EventGroup,
                          ServerEvent as _ServerEvent, SocketIO as _SocketIO)


class BaseEventGroup(_EventGroup, DatabaseSearcherMixin, JWTAuthorizerMixin, metaclass=ABCMeta):
    pass


@dataclass
class EventException(Exception):
    code: int
    message: str
    critical: bool = False


class ServerEvent(_ServerEvent):
    def emit(self, _room: str = None, _include_self: bool = True, _data: ... = None, _namespace: str = None, **kwargs):
        if issubclass(self.model, PydanticModel) and _data is not None:
            _data = self.model.convert(_data, **kwargs)
        return super().emit(_room, _include_self, _data, _namespace, **kwargs)


class EventGroup(BaseEventGroup, metaclass=ABCMeta):
    ServerEvent = ServerEvent

    def __init__(self, sessionmaker: Sessionmaker, use_kebab_case: bool = False):
        super().__init__(use_kebab_case)
        self.sessionmaker = sessionmaker

    def with_begin(self, function):
        return self.sessionmaker.with_begin(function)

    def _bind_model(self, bound_model: Type[BaseModel]):
        if issubclass(bound_model, PydanticModel):
            bound_model.Config.title = bound_model.name
        super()._bind_model(bound_model)

    def doc_abort(self, error_code: Union[int, str], description: str, *, critical: bool = False):
        def doc_abort_wrapper(function):
            return function

        return doc_abort_wrapper

    @staticmethod
    def _get_model_name(bound_model: Type[BaseModel]):
        if isinstance(bound_model, type) and issubclass(bound_model, Nameable):
            return bound_model.name or bound_model.__name__
        return bound_model.__name__

    @staticmethod
    def _get_model_schema(bound_model: Type[BaseModel]):
        if issubclass(bound_model, PydanticModel):
            return {"payload": Model(EventGroup._get_model_name(bound_model), bound_model.model()).__schema__}
        return {"payload": bound_model.schema()}

    def abort(self, error_code: Union[int, str], description: str, *, critical: bool = False, **kwargs):
        raise EventException(error_code, description, critical)


class Namespace(_Namespace):
    def __init__(self, namespace=None, protected: str | bool = False):
        super().__init__(namespace)
        if protected is not False:
            if protected is True:
                protected = ""

            @self.on_connect()
            @jwt_required(optional=True)
            def user_connect(*_):
                identity = get_jwt_identity()
                if identity is None or (user_id := identity.get(protected, None)) is None:
                    raise ConnectionRefusedError("unauthorized!")
                join_room(f"user-{user_id}")

    def handle_exception(self, exception: EventException):
        pass

    def trigger_event(self, event, *args):
        try:
            return super().trigger_event(event.replace("-", "_"), *args)
        except EventException as e:
            self.handle_exception(e)
            if e.critical:
                disconnect()


class CustomJSON:
    def default(self, value: ...) -> ...:
        if isinstance(value, TypeEnum):
            return value.to_string()
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def dumps(self, *args, **kwargs):
        return dumps(*args, default=self.default, **kwargs)

    def loads(self, *args, **kwargs):
        return loads(*args, **kwargs)


class SocketIO(_SocketIO):
    def __init__(self, *args, **kwargs):
        if "json" not in kwargs:
            kwargs["json"] = CustomJSON
        super().__init__(*args, **kwargs)

#     def __init__(self, app=None, title: str = "SIO", version: str = "1.0.0", doc_path: str = "/doc/", **kwargs):
#         super().__init__(app, title, version, doc_path, **kwargs)
#
#         @self.on("connect")  # TODO check everytime or save in session?
#         def connect_user():  # https://python-socketio.readthedocs.io/en/latest/server.html#user-sessions
#             pass             # sio = main.socketio.server
