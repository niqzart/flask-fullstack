from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from logging import Filter, getLogger
from typing import Type, Iterable

from flask_socketio import Namespace as _Namespace, SocketIO as _SocketIO
from pydantic import BaseModel

from .events import ClientEvent, ServerEvent, DuplexEvent, BaseEvent
from .utils import remove_none


def kebabify_model(model: Type[BaseModel]):
    for f_name, field in model.__fields__.items():
        if field.alias == f_name:
            field.alias = field.name.replace("_", "-")


@dataclass
class BoundEvent:
    event: BaseEvent
    model: Type[BaseModel]
    handler: Callable = None
    additional_docs: dict = None


class EventGroup:
    ClientEvent: Type[ClientEvent] = ClientEvent
    ServerEvent: Type[ServerEvent] = ServerEvent
    DuplexEvent: Type[DuplexEvent] = DuplexEvent

    def __init__(self, namespace: str = None, use_kebab_case: bool = False):
        self.use_kebab_case: bool = use_kebab_case
        self.bound_events: list[BoundEvent] = []
        self.bound_models: list[Type[BaseModel]] = []
        self.namespace: str | None = namespace

    @staticmethod
    def _kebabify(name: str | None, model: Type[BaseModel]) -> str | None:
        kebabify_model(model)
        if name is None:
            return None
        return name.replace("_", "-")

    def _get_event_name(self, bound_event: BoundEvent):
        if self.use_kebab_case:
            return bound_event.event.name.replace("_", "-")
        return bound_event.event.name

    def _get_model_reference(self, bound_event: BoundEvent, namespace: str = None):
        return bound_event.event.create_doc(namespace or self.namespace or "/", bound_event.additional_docs)

    def extract_doc_channels(self, namespace: str = None) -> OrderedDict[str, ...]:
        return OrderedDict((self._get_event_name(bound_event), self._get_model_reference(bound_event, namespace))
                           for bound_event in self.bound_events)

    @staticmethod
    def _get_model_name(bound_model: Type[BaseModel]):
        return bound_model.__name__

    @staticmethod
    def _get_model_schema(bound_model: Type[BaseModel]):
        return {"payload": bound_model.schema(ref_template="#/components/messages/{model}")}

    def extract_doc_messages(self) -> OrderedDict[str, ...]:
        return OrderedDict((self._get_model_name(bound_model), self._get_model_schema(bound_model))
                           for bound_model in self.bound_models)

    def extract_handlers(self) -> Iterable[tuple[str, Callable]]:
        for bound_event in self.bound_events:
            yield bound_event.event.name, bound_event.handler

    def _bind_event(self, bound_event: BoundEvent):
        self.bound_events.append(bound_event)

    def _bind_model(self, bound_model: Type[BaseModel]):
        self.bound_models.append(bound_model)

    def bind_pub_full(self, event: ClientEvent) -> Callable[[Callable], ClientEvent]:
        if self.namespace is not None:
            event.attach_namespace(self.namespace)
        kebabify_model(event.model)
        self._bind_model(event.model)

        def bind_pub_wrapper(function) -> ClientEvent:
            def handler(data=None):
                return function(None, **event.model.parse_obj(data).dict())  # TODO temp, pass self or smth

            self._bind_event(BoundEvent(event, event.model, handler, getattr(function, "__sio_doc__", None)))
            return event

        return bind_pub_wrapper

    def bind_pub(self, model: Type[BaseModel], ack_model: Type[BaseModel] = None, *, description: str = None,
                 name: str = None) -> Callable[[Callable], ClientEvent]:
        if self.use_kebab_case and name is not None:
            name = name.replace("_", "-")
        return self.bind_pub_full(self.ClientEvent(model, ack_model, name, description))

    def bind_sub_full(self, event: ServerEvent) -> ServerEvent:
        if self.namespace is not None:
            event.attach_namespace(self.namespace)
        kebabify_model(event.model)
        self._bind_event(BoundEvent(event, event.model))
        self._bind_model(event.model)
        return event

    def bind_sub(self, model: Type[BaseModel], *, description: str = None, name: str = None) -> ServerEvent:
        if self.use_kebab_case and name is not None:
            name = name.replace("_", "-")
        return self.bind_sub_full(self.ServerEvent(model, name, description))

    def bind_dup_full(self, event: DuplexEvent, same_model: bool = True,
                      use_event: bool = False) -> Callable[[Callable], DuplexEvent]:
        if self.namespace is not None:
            event.attach_namespace(self.namespace)
        kebabify_model(event.client_event.model)
        kebabify_model(event.server_event.model)
        self._bind_model(event.client_event.model)
        if not same_model:
            self._bind_model(event.server_event.model)

        def bind_dup_wrapper(function) -> DuplexEvent:
            def handler(*args):
                data = args[-1]
                args = list(args)  # TODO accurate is: list(args[:-1])
                if use_event:
                    args.append(event)
                return function(*args, **event.client_event.model.parse_obj(data).dict())

            self._bind_event(BoundEvent(event, event.client_event.model,
                                        handler, getattr(function, "__sio_doc__", None)))
            return event

        return bind_dup_wrapper

    def bind_dup(self, model: Type[BaseModel], server_model: Type[BaseModel] = None,
                 ack_model: Type[BaseModel] = None, *, description: str = None,
                 name: str = None, use_event: bool = False) -> Callable[[Callable], DuplexEvent]:
        if self.use_kebab_case and name is not None:
            name = name.replace("_", "-")

        same_model: bool = server_model is None
        if same_model:
            server_model = model
        else:
            if self.use_kebab_case:
                kebabify_model(server_model)
            self._bind_model(server_model)

        event = self.DuplexEvent(
            self.ClientEvent(model, ack_model, name, description),
            self.ServerEvent(server_model, name, description),
            description=description
        )
        return self.bind_dup_full(event, same_model, use_event)

    def attach_namespace(self, namespace: str):
        self.namespace = namespace
        for event in self.bound_events:
            event.event.attach_namespace(namespace)

    @staticmethod
    def update_event_data(function: Callable, data: dict) -> Callable:
        if hasattr(function, "__event_data__"):
            function.__event_data__.update(data)
        else:
            function.__event_data__ = data
        return function

    @staticmethod
    def updates_event_data(**data) -> Callable[[Callable], Callable]:
        data = remove_none(data)

        def updates_event_data_inner(function):
            return EventGroup.update_event_data(function, data)

        return updates_event_data_inner

    def argument_parser(self, model: Type[BaseModel]) -> Callable[[Callable], Callable]:
        return self.updates_event_data(model=model)

    def mark_duplex(self, server_model: Type[BaseModel] = None) -> Callable[[Callable], Callable]:
        return self.updates_event_data(server_model=server_model, duplex=True)

    def marshal_ack(self, ack_model: Type[BaseModel]) -> Callable[[Callable], Callable]:
        # TODO ack parameters + replace defaults with None
        return self.updates_event_data(ack_model=ack_model)

    def render_event_data(self, event_data: dict) -> ClientEvent | DuplexEvent:
        client_model = event_data.get("model", BaseModel)
        client_event = self.ClientEvent(client_model, event_data.get("ack_model", None))

        if event_data.get("duplex", False):
            return self.DuplexEvent(client_event, self.ServerEvent(event_data.get("server_model", client_model)))

        return client_event

    def route(self, cls: type | None = None) -> type:  # TODO mb move data pre- and post-processing from modes to here
        def route_inner(cls: type) -> type:
            for name, value in cls.__dict__.items():
                if callable(value):
                    event_data: dict = getattr(value, "__event_data__", None)
                    if event_data is None:
                        continue
                    value = self.render_event_data(event_data)

                if isinstance(value, BaseEvent) and value.name is None:
                    value.attach_name(name.replace("_", "-") if self.use_kebab_case else name)
                    if self.namespace is not None:
                        value.attach_namespace(self.namespace)

                setattr(cls, name, value)

            return cls

        return route_inner if cls is None else route_inner(cls)


class EventSpace:
    pass


class Namespace(_Namespace):
    def __init__(self, namespace: str = None, use_kebab_case: bool = False):
        super().__init__(namespace)
        self.doc_channels = OrderedDict()
        self.doc_messages = OrderedDict()
        self.use_kebab_case = use_kebab_case

    def attach_event_group(self, event_group: EventGroup):
        event_group.attach_namespace(self.namespace)
        self.doc_channels.update(event_group.extract_doc_channels())
        self.doc_messages.update(event_group.extract_doc_messages())
        for name, handler in event_group.extract_handlers():
            if self.use_kebab_case:
                name = name.replace("-", "_")
            setattr(self, f"on_{name}", handler)

    def on_event(self, name: str):
        def on_event_wrapper(function: Callable[[...], None]):
            setattr(self, f"on_{name}", function)

        return on_event_wrapper

    def on_connect(self, function: Callable[[...], None] | None = None):
        if function is None:
            def on_connect_wrapper(function: Callable[[...], None]):
                setattr(self, f"on_connect", function)

            return on_connect_wrapper

        setattr(self, f"on_connect", function)

    def on_disconnect(self, function: Callable[[...], None] = None):
        if function is None:
            def on_disconnect_wrapper(function: Callable[[...], None]):
                setattr(self, f"on_disconnect", function)

            return on_disconnect_wrapper

        setattr(self, f"on_disconnect", function)

    def attach_event_space(self, cls: Type[EventSpace]):
        cls.event_group.attach_namespace(self.namespace)
        return cls


class NoPingPongFilter(Filter):
    def filter(self, record):
        return not ("Received packet PONG" in record.getMessage() or "Sending packet PING" in record.getMessage())


class SocketIO(_SocketIO):
    def __init__(self, app=None, title: str = "SIO", version: str = "1.0.0", doc_path: str = "/sio-doc/",
                 remove_ping_pong_logs: bool = False, **kwargs):
        self.async_api = {"asyncapi": "2.2.0", "info": {"title": title, "version": version},
                          "channels": OrderedDict(), "components": {"messages": OrderedDict()}}
        self.doc_path = doc_path
        if remove_ping_pong_logs:
            getLogger("engineio.server").addFilter(NoPingPongFilter())
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
