from abc import ABCMeta
from dataclasses import dataclass
from typing import Union

from flask_restx import Model as BaseModel
from flask_socketio import disconnect

from .marshals import PydanticModel, Model
from .mixins import DatabaseSearcherMixin, JWTAuthorizerMixin
from .sqlalchemy import Sessionmaker
from .utils import Nameable
from ..flask_siox import Namespace as _Namespace, EventGroup as _EventGroup
from ..flask_siox.structures import BoundEvent


class BaseEventGroup(_EventGroup, DatabaseSearcherMixin, JWTAuthorizerMixin, metaclass=ABCMeta):
    pass


@dataclass
class EventException(Exception):
    code: int
    message: str
    critical: bool = False


class EventGroup(BaseEventGroup, metaclass=ABCMeta):
    def __init__(self, sessionmaker: Sessionmaker, use_kebab_case: bool = False):
        super().__init__(use_kebab_case)
        self.sessionmaker = sessionmaker

    def with_begin(self, function):
        return self.sessionmaker.with_begin(function)

    def _bind_event(self, bound_event: BoundEvent):
        if issubclass(bound_event.model, Nameable):
            bound_event.event.attach_model_name(bound_event.model.name)
        if issubclass(bound_event.model, PydanticModel):
            bound_event.model.Config.title = bound_event.model.name
        self.bound_events.append(bound_event)

    @staticmethod
    def _get_model_schema(bound_event: BoundEvent):
        if issubclass(bound_event.model, Model):
            return {"payload": BaseModel(EventGroup._get_model_name(bound_event), bound_event.model.model()).__schema__}
        return {"payload": bound_event.model.schema()}

    def abort(self, error_code: Union[int, str], description: str, *, critical: bool = False, **kwargs):
        raise EventException(error_code, description, critical)


class Namespace(_Namespace):
    def handle_exception(self, exception: EventException):
        pass

    def trigger_event(self, event, *args):
        try:
            super().trigger_event(event.replace("-", "_"), *args)
        except EventException as e:
            self.handle_exception(e)
            if e.critical:
                disconnect()

# class SocketIO(_SocketIO):
#     def __init__(self, app=None, title: str = "SIO", version: str = "1.0.0", doc_path: str = "/doc/", **kwargs):
#         super().__init__(app, title, version, doc_path, **kwargs)
#
#         @self.on("connect")  # TODO check everytime or save in session?
#         def connect_user():  # https://python-socketio.readthedocs.io/en/latest/server.html#user-sessions
#             pass             # sio = main.socketio.server
