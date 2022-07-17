from __future__ import annotations

from abc import ABCMeta
from datetime import datetime
from functools import wraps
from json import dumps, loads
from typing import Union, Type, Callable

from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restx import Model
from flask_socketio import join_room
from pydantic import BaseModel
from socketio.exceptions import ConnectionRefusedError

from .marshals import PydanticModel
from .mixins import DatabaseSearcherMixin, JWTAuthorizerMixin
from .sqlalchemy import Sessionmaker
from .utils import Nameable, TypeEnum
from ..flask_siox import (ClientEvent as _ClientEvent, ServerEvent as _ServerEvent, DuplexEvent as _DuplexEvent,
                          EventGroupBase as _EventGroupBase, EventException, EventGroup as _EventGroup,
                          EventController as _EventController, Namespace as _Namespace, SocketIO as _SocketIO)


class EventGroupBaseMixedIn(_EventGroupBase, DatabaseSearcherMixin, JWTAuthorizerMixin, metaclass=ABCMeta):
    pass


class ClientEvent(_ClientEvent):
    def __init__(self, model: Type[BaseModel], ack_model: Type[BaseModel] = None, namespace: str = None,
                 name: str = None, description: str = None, handler: Callable = None,
                 include: set[str] = None, exclude: set[str] = None, exclude_none: bool = None,
                 force_wrap: bool = None, force_ack: bool = None, additional_docs: dict = None):
        super().__init__(model, ack_model, namespace, name, description, handler, include, exclude,
                         exclude_none, force_wrap is not False, force_ack is not False, additional_docs)

    def _force_wrap(self, data) -> dict:
        result = {"code": 200, "message": "Success"}
        if isinstance(data, str):
            result["message"] = data
        elif data is not None:
            result["data"] = data
        return result

    def parse(self, data=None) -> dict:
        if data is None:
            return {}
        if isinstance(self.model, type) and issubclass(self.model, PydanticModel):
            return self.model.deconvert(data).dict()
        return super().parse(data)


class ServerEvent(_ServerEvent):
    def emit(self, _room: str = None, _include_self: bool = True, _broadcast: bool = True,
             _data: ... = None, _namespace: str = None, **kwargs):
        if isinstance(self.model, type) and issubclass(self.model, PydanticModel) and _data is not None:
            _data = self.model.convert(_data, **kwargs)
        return super().emit(_room, _include_self, _broadcast, _data, _namespace, **kwargs)

    def emit_convert(self, data: ... = None, room: str = None, include_self: bool = None,
                     user_id: int = None, namespace: str = None, broadcast: bool = None, **kwargs):
        if user_id is not None:
            room = f"user-{user_id}"
        if include_self is None:
            include_self = False
        if broadcast is None:
            broadcast = False
        return self.emit(_data=data, _room=room, _include_self=include_self,
                         _broadcast=broadcast, _namespace=namespace, **kwargs)


class DuplexEvent(_DuplexEvent):
    server_event: ServerEvent

    def emit_convert(self, data: ... = None, room: str = None, include_self: bool = None,
                     user_id: int = None, namespace: str = None, broadcast: bool = None, **kwargs):
        self.server_event.emit_convert(data, room, include_self, user_id, namespace, broadcast, **kwargs)


class EventGroupBase(EventGroupBaseMixedIn):
    ClientEvent = ClientEvent
    ServerEvent = ServerEvent
    DuplexEvent = DuplexEvent

    def __init__(self, sessionmaker: Sessionmaker, namespace: str = None, use_kebab_case: bool = False):
        super().__init__(namespace, use_kebab_case)
        self.sessionmaker = sessionmaker

    def with_begin(self, function):
        return self.sessionmaker.with_begin(function)

    def _bind_model(self, bound_model: Type[BaseModel]):
        if isinstance(bound_model, type) and issubclass(bound_model, PydanticModel):
            bound_model.Config.title = bound_model.name
        super()._bind_model(bound_model)

    def doc_abort(self, error_code: Union[int, str], description: str, *, critical: bool = False):
        def doc_abort_wrapper(function):
            return function

        return doc_abort_wrapper

    def _get_model_name(self, bound_model: Type[BaseModel]):
        if isinstance(bound_model, type) and issubclass(bound_model, Nameable):
            return bound_model.name or bound_model.__name__
        return super()._get_model_name(bound_model)

    def _get_model_schema(self, bound_model: Type[BaseModel]):
        if isinstance(bound_model, type) and issubclass(bound_model, PydanticModel):
            return {"payload": Model(self._get_model_name(bound_model), bound_model.model()).__schema__}
        return super()._get_model_schema(bound_model)

    def abort(self, error_code: Union[int, str], description: str, *, critical: bool = False, **kwargs):
        raise EventException(error_code, description, critical)


class EventGroup(_EventGroup, EventGroupBase):  # DEPRECATED
    pass


class EventController(_EventController, EventGroupBase):
    def _marshal_ack_wrapper(self, ack_model: Type[BaseModel], ack_kwargs: dict, function: Callable) -> Callable:
        if isinstance(ack_model, type) and issubclass(ack_model, PydanticModel):
            model: Type[PydanticModel] = ack_model

            @wraps(function)
            def marshal_ack_inner(*args, **kwargs):
                result = function(*args, **kwargs)
                if not isinstance(result, ack_model):
                    result = model.convert(result, **kwargs)
                return result
        else:
            marshal_ack_inner = function

        return super()._marshal_ack_wrapper(ack_model, ack_kwargs, marshal_ack_inner)


class Namespace(_Namespace):
    def __init__(self, namespace: str = None, protected: str | bool = False, use_kebab_case: bool = False):
        super().__init__(namespace, use_kebab_case)
        self.mark_protected(protected)

    def mark_protected(self, protected: str | bool = False):
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


class CustomJSON:
    @staticmethod
    def default(value: ...) -> ...:
        if isinstance(value, TypeEnum):
            return value.to_string()
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError(f"Type {type(value)} not serializable")

    @staticmethod
    def dumps(*args, **kwargs):
        return dumps(*args, default=CustomJSON.default, **kwargs)

    @staticmethod
    def loads(*args, **kwargs):
        return loads(*args, **kwargs)


class SocketIO(_SocketIO):
    default_namespace_class = Namespace

    def __init__(self, *args, **kwargs):
        if "json" not in kwargs:
            kwargs["json"] = CustomJSON()
        super().__init__(*args, **kwargs)

    def add_namespace(self, name: str = None, *event_groups: EventGroupBase, protected: str | bool = False):
        namespace = self.namespace_class(name, self.use_kebab_case)
        if isinstance(namespace, Namespace):
            namespace.mark_protected(protected)
        self._add_namespace(namespace, *event_groups)

#     def __init__(self, app=None, title: str = "SIO", version: str = "1.0.0", doc_path: str = "/doc/", **kwargs):
#         super().__init__(app, title, version, doc_path, **kwargs)
#
#         @self.on("connect")  # TODO check everytime or save in session?
#         def connect_user():  # https://python-socketio.readthedocs.io/en/latest/server.html#user-sessions
#             pass             # sio = main.socketio.server
