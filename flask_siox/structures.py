from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Type, Iterable

from flask_socketio import Namespace as _Namespace, SocketIO as _SocketIO
from pydantic import BaseModel

from .events import ClientEvent, ServerEvent, DuplexEvent, BaseEvent


def kebabify_model(model: Type[BaseModel]):
    for f_name, field in model.__fields__.items():
        field.alias = field.name.replace("_", "-")


@dataclass
class BoundEvent:
    event: BaseEvent
    model: Type[BaseModel]
    function: Callable = None
    additional_docs: dict = None

    def handler(self, data=None):
        return self.function(**self.model.parse_obj(data).dict())

    def create_doc(self, namespace: str = None):
        return self.event.create_doc(namespace or "/", self.additional_docs)


class EventGroup:
    def __init__(self, use_kebab_case: bool = False):
        self.use_kebab_case: bool = use_kebab_case
        self.bound_events: list[BoundEvent] = []

    @staticmethod
    def _kebabify(name: str | None, model: Type[BaseModel]) -> str | None:
        kebabify_model(model)
        if name is None:
            return None
        return name.replace("_", "-")

    def _get_model_name(self, bound_event: BoundEvent):
        return bound_event.model.__qualname__

    def extract_doc_channels(self, namespace: str = None) -> OrderedDict[str, ...]:
        return OrderedDict((bound_event.event.name, bound_event.create_doc(namespace))
                           for bound_event in self.bound_events)

    def extract_doc_messages(self) -> OrderedDict[str, ...]:
        return OrderedDict((self._get_model_name(bound_event), {"payload": bound_event.model.schema()})
                           for bound_event in self.bound_events)

    def extract_handlers(self) -> Iterable[tuple[str, Callable]]:
        for bound_event in self.bound_events:
            yield bound_event.event.name, bound_event.handler

    def bind_pub(self, model: Type[BaseModel], *, description: str = None,
                 name: str = None) -> Callable[[Callable], ClientEvent]:
        if self.use_kebab_case:
            name = self._kebabify(name, model)
        event = ClientEvent(model, name, description)

        def bind_pub_wrapper(function) -> ClientEvent:
            self.bound_events.append(BoundEvent(event, model, function, getattr(function, "__sio_doc__", None)))
            return event

        return bind_pub_wrapper

    def bind_sub(self, model: Type[BaseModel], *, description: str = None, name: str = None) -> ServerEvent:
        if self.use_kebab_case:
            name = self._kebabify(name, model)
        event = ServerEvent(model, name, description)
        self.bound_events.append(BoundEvent(event, model))
        return event

    def bind_dup(self, model: Type[BaseModel], *, description: str = None,
                 name: str = None) -> Callable[[Callable], DuplexEvent]:
        if self.use_kebab_case:
            name = self._kebabify(name, model)
        event = DuplexEvent.similar(model, name)
        event.description = description

        def bind_dup_wrapper(function) -> DuplexEvent:
            self.bound_events.append(BoundEvent(event, model, function, getattr(function, "__sio_doc__", None)))
            return event

        return bind_dup_wrapper


class EventSpaceMeta(type):
    def __init__(cls, name: str, bases: tuple[type, ...], namespace: dict[str, ...]):
        for name, value in namespace.items():
            if isinstance(value, BaseEvent) and value.name is None:
                value.attach_name(name)
        super().__init__(name, bases, namespace)


class EventSpace(metaclass=EventSpaceMeta):
    pass


class Namespace(_Namespace):
    def __init__(self, namespace=None):
        super().__init__(namespace)
        self.doc_channels = OrderedDict()
        self.doc_messages = OrderedDict()

    def attach_event_group(self, event_group: EventGroup):
        self.doc_channels.update(event_group.extract_doc_channels())
        self.doc_messages.update(event_group.extract_doc_messages())
        for name, handler in event_group.extract_handlers():
            setattr(self, f"on_{name.replace('-', '_')}", handler)


class SocketIO(_SocketIO):
    def __init__(self, app=None, title: str = "SIO", version: str = "1.0.0", doc_path: str = "/doc/", **kwargs):
        self.async_api = {"asyncapi": "2.2.0", "info": {"title": title, "version": version},
                          "channels": OrderedDict(), "components": {"messages": OrderedDict()}}
        self.doc_path = doc_path
        super(SocketIO, self).__init__(app, **kwargs)

    def docs(self):
        return self.async_api

    def init_app(self, app, **kwargs):
        app.config["JSON_SORT_KEYS"] = False  # TODO kinda bad for a library

        @app.route(self.doc_path)
        def documentation():
            return self.docs()

        return super(SocketIO, self).init_app(app, **kwargs)

    def on_namespace(self, namespace_handler):
        if isinstance(namespace_handler, Namespace):
            self.async_api["channels"].update(namespace_handler.doc_channels)
            self.async_api["components"]["messages"].update(namespace_handler.doc_messages)
        return super(SocketIO, self).on_namespace(namespace_handler)
