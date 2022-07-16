from __future__ import annotations

from collections import OrderedDict
from typing import Type, Callable, Iterable

from pydantic import BaseModel

from .events import ClientEvent, DuplexEvent, BaseEvent
from .interfaces import EventGroupBase
from .utils import kebabify_model


class EventController(EventGroupBase):
    def __init__(self, namespace: str = None, use_kebab_case: bool = False):
        super().__init__(namespace, use_kebab_case)
        self.bound_events: list[BaseEvent] = []

    def _get_event_name(self, event: BaseEvent):
        if self.use_kebab_case:
            return event.name.replace("_", "-")
        return event.name

    def _create_doc(self, event: BaseEvent):
        return event.create_doc(self.namespace or "/")  # , event.additional_docs)

    def extract_doc_channels(self) -> OrderedDict[str, ...]:
        return OrderedDict((self._get_event_name(event), self._create_doc(event)) for event in self.bound_events)

    def extract_handlers(self) -> Iterable[tuple[str, Callable]]:
        for event in self.bound_events:
            if isinstance(event, ClientEvent):
                yield event.name, event.handler
            elif isinstance(event, DuplexEvent):
                yield event.client_event.name, event.client_event.handler

    def attach_namespace(self, namespace: str):
        for event in self.bound_events:
            event.attach_namespace(namespace)

    model_kwarg_names = ("include", "exclude", "exclude_none")
    ack_kwarg_names = {n: "ack_" + n for n in model_kwarg_names + ("force_wrap",)}

    @staticmethod
    def _update_event_data(function: Callable, data: dict) -> Callable:
        if hasattr(function, "__event_data__"):
            function.__event_data__.update(data)
        else:
            function.__event_data__ = data
        return function

    def _maybe_bind_model(self, model: Type[BaseModel] | None = None) -> None:
        if model is None:
            return
        if self.use_kebab_case:
            kebabify_model(model)
        self._bind_model(model)

    def argument_parser(self, client_model: Type[BaseModel] = BaseModel):
        self._maybe_bind_model(client_model)

        def argument_parser_wrapper(function: Callable) -> ClientEvent | DuplexEvent:
            event_data: dict = getattr(function, "__event_data__", {})
            ack_kwargs = {n: event_data.get(v, None) for n, v in self.ack_kwarg_names.items()}
            client_event = self.ClientEvent(client_model, event_data.get("ack_model", None), **ack_kwargs)
            client_event.bind(function)

            if event_data.get("duplex", False):
                server_kwargs = {n: event_data.get(n, None) for n in self.model_kwarg_names}
                server_event = self.ServerEvent(event_data.get("server_model", client_model), **server_kwargs)
                return self.DuplexEvent(client_event, server_event, event_data.get("use_event", None))

            return client_event

        return argument_parser_wrapper

    def mark_duplex(self, server_model: Type[BaseModel] = None, use_event: bool = None,
                    include: set[str] = None, exclude: set[str] = None, exclude_none: bool = None):
        self._maybe_bind_model(server_model)

        # TODO clearly label: Callable -> Callable & ClientEvent -> DuplexEvent
        def mark_duplex_wrapper(value: Callable | ClientEvent) -> Callable | DuplexEvent:
            server_kwargs = {"include": include, "exclude": exclude,
                             "exclude_none": exclude_none, "use_event": use_event}
            if isinstance(value, ClientEvent):
                server_event = self.ServerEvent(server_model, **server_kwargs)
                return self.DuplexEvent(value, server_event)
            return self._update_event_data(value, dict(server_kwargs, duplex=True, server_model=server_model))

        return mark_duplex_wrapper

    def marshal_ack(self, ack_model: Type[BaseModel], include: set[str] = None, exclude: set[str] = None,
                    force_wrap: bool = None, exclude_none: bool = None):
        self._maybe_bind_model(ack_model)

        # TODO clearly label: Callable -> Callable & ClientEvent -> ClientEvent & DuplexEvent -> DuplexEvent
        def marshal_ack_wrapper(value: Callable | ClientEvent | DuplexEvent) -> Callable | ClientEvent | DuplexEvent:
            if isinstance(value, DuplexEvent):
                value.client_event.attach_ack(ack_model, include, exclude, force_wrap, exclude_none)
            elif isinstance(value, ClientEvent):
                value.attach_ack(ack_model, include, exclude, force_wrap, exclude_none)
            else:
                ack_kwargs = {"ack_include": include, "ack_exclude": exclude,
                              "ack_exclude_none": exclude_none, "ack_force_wrap": force_wrap}
                value = self._update_event_data(value, ack_kwargs)
            return value

        return marshal_ack_wrapper

    def route(self, cls: type | None = None) -> type:  # TODO mb move data pre- and post-processing from modes to here
        def route_inner(cls: type) -> type:
            for name, value in cls.__dict__.items():
                if isinstance(value, BaseEvent):
                    if value.name is None:
                        value.attach_name(name.replace("_", "-") if self.use_kebab_case else name)
                    if self.namespace is not None:
                        value.attach_namespace(self.namespace)
                    self.bound_events.append(value)

                setattr(cls, name, value)

            return cls

        return route_inner if cls is None else route_inner(cls)


class EventSpace:
    pass
