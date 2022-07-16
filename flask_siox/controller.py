from __future__ import annotations

from functools import wraps
from typing import Type, Callable

from pydantic import BaseModel

from .events import ClientEvent, DuplexEvent, BaseEvent
from .interfaces import EventGroupBase
from .utils import kebabify_model


class EventController(EventGroupBase):
    model_kwarg_names = ("include", "exclude", "exclude_none")
    ack_kwarg_names = {n: "ack_" + n for n in model_kwarg_names + ("force_wrap",)}
    ack_kwarg_names["force_ack"] = "force_ack"

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

    def add_docs(self, additional_docs: dict):
        # TODO clearly label: Callable -> Callable & ClientEvent -> ClientEvent & DuplexEvent -> DuplexEvent
        def add_docs_wrapper(function: Callable | ClientEvent | DuplexEvent) -> Callable | ClientEvent | DuplexEvent:
            if isinstance(function, BaseEvent):
                if function.additional_docs is None:
                    function.additional_docs = additional_docs
                else:
                    function.additional_docs.update(additional_docs)
            else:
                self._update_event_data(function, {"additional_docs": additional_docs})

            return function

        return add_docs_wrapper

    def argument_parser(self, client_model: Type[BaseModel] = BaseModel):
        self._maybe_bind_model(client_model)

        def argument_parser_wrapper(function: Callable) -> ClientEvent | DuplexEvent:
            event_data: dict = getattr(function, "__event_data__", {})
            additional_docs: dict = getattr(function, "additional_docs", {})

            ack_kwargs = {n: event_data.get(v, None) for n, v in self.ack_kwarg_names.items()}
            client_event = self.ClientEvent(client_model, event_data.get("ack_model", None), **ack_kwargs)

            if event_data.get("duplex", False):
                server_kwargs = {n: event_data.get(n, None) for n in self.model_kwarg_names}
                server_event = self.ServerEvent(event_data.get("server_model", client_model), **server_kwargs)
                duplex_event = self.DuplexEvent(client_event, server_event, event_data.get("use_event", None),
                                                additional_docs=additional_docs)
                duplex_event.bind(function)
                return duplex_event

            client_event.bind(function)
            client_event.additional_docs = additional_docs
            return client_event

        return argument_parser_wrapper

    def mark_duplex(self, server_model: Type[BaseModel] = None, use_event: bool = None,
                    include: set[str] = None, exclude: set[str] = None, exclude_none: bool = None):
        self._maybe_bind_model(server_model)
        server_kwargs = {"include": include, "exclude": exclude,
                         "exclude_none": exclude_none, "use_event": use_event}

        # TODO clearly label: Callable -> Callable & ClientEvent -> DuplexEvent
        def mark_duplex_wrapper(value: Callable | ClientEvent) -> Callable | DuplexEvent:
            if isinstance(value, ClientEvent):
                server_event = self.ServerEvent(server_model, **server_kwargs)
                return self.DuplexEvent(value, server_event)
            return self._update_event_data(value, dict(server_kwargs, duplex=True, server_model=server_model))

        return mark_duplex_wrapper

    def _marshal_ack_wrapper(self, ack_model: Type[BaseModel], ack_kwargs: dict, function: Callable) -> Callable:
        return self._update_event_data(function, dict(ack_kwargs, ack_model=ack_model))

    def marshal_ack(self, ack_model: Type[BaseModel], include: set[str] = None, exclude: set[str] = None,
                    force_wrap: bool = None, exclude_none: bool = None):
        self._maybe_bind_model(ack_model)
        ack_kwargs = {"ack_include": include, "ack_exclude": exclude,
                      "ack_exclude_none": exclude_none, "ack_force_wrap": force_wrap}

        def marshal_ack_wrapper(function: Callable) -> Callable:
            return self._marshal_ack_wrapper(ack_model, ack_kwargs, function)

        return marshal_ack_wrapper

    def force_ack(self, force_wrap: bool = None):
        def force_ack_wrapper(function: Callable) -> Callable:
            return self._update_event_data(function, {"force_ack": True, "ack_force_wrap": force_wrap})

        return force_ack_wrapper

    def with_cls(self, cls: type, function: Callable):
        @wraps(function)
        def with_cls_inner(*args, **kwargs):
            return function(cls, *args, **kwargs)

        return with_cls_inner

    def route(self, cls: type | None = None) -> type:  # TODO mb move data pre- and post-processing from modes to here
        def route_inner(cls: type) -> type:
            for name, value in cls.__dict__.items():
                if isinstance(value, BaseEvent):
                    if isinstance(value, ClientEvent):
                        value.handler = self.with_cls(cls, value.handler)
                    elif isinstance(value, DuplexEvent):
                        value.client_event.handler = self.with_cls(cls, value.client_event.handler)

                    if value.name is None:
                        value.attach_name(name.replace("_", "-") if self.use_kebab_case else name)
                    if self.namespace is not None:
                        value.attach_namespace(self.namespace)
                    self._bind_event(value)

                setattr(cls, name, value)

            return cls

        return route_inner if cls is None else route_inner(cls)


class EventSpace:
    pass
