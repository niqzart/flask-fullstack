from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from pydantic import BaseModel as BaseModelV2
from pydantic.v1 import BaseModel
from pydantic_marshals.utils import is_subtype

from .events import BaseEvent, ClientEvent, DuplexEvent
from .interfaces import EventGroupBase
from ..restx.marshals import v2_model_to_ffs
from ..utils import kebabify_model


class EventController(EventGroupBase):
    server_kwarg_names = ("include", "exclude", "exclude_none")
    client_kwarg_names = {n: f"ack_{n}" for n in server_kwarg_names + ("force_wrap",)}
    client_kwarg_names["force_ack"] = "force_ack"
    client_kwarg_names["additional_models"] = "additional_models"

    @staticmethod
    def _update_event_data(function: Callable, data: dict) -> Callable:
        if hasattr(function, "__event_data__"):
            function.__event_data__.update(data)
        else:
            function.__event_data__ = data
        return function

    def _maybe_bind_model(self, model: type[BaseModel] | None = None) -> None:
        if model is None:
            return
        if self.use_kebab_case:
            kebabify_model(model)
        self._bind_model(model)

    def argument_parser(
        self, client_model: type[BaseModel] | type[BaseModelV2] = BaseModel
    ):
        if is_subtype(client_model, BaseModelV2):
            client_model = v2_model_to_ffs(client_model, optional=True)

        self._maybe_bind_model(client_model)

        def argument_parser_wrapper(function: Callable) -> ClientEvent | DuplexEvent:
            event_data: dict = getattr(function, "__event_data__", {})

            client_kwargs = {
                n: event_data.get(v, None) for n, v in self.client_kwarg_names.items()
            }
            client_event = self.ClientEvent(
                client_model,
                event_data.get("ack_model", None),
                **client_kwargs,
            )

            if event_data.get("duplex", False):
                server_kwargs = {
                    n: event_data.get(n, None) for n in self.server_kwarg_names
                }
                server_event = self.ServerEvent(
                    event_data.get("server_model", None) or client_model,
                    **server_kwargs,
                )
                duplex_event = self.DuplexEvent(
                    client_event,
                    server_event,
                    event_data.get("use_event", None),
                )
                duplex_event.bind(function)
                return duplex_event

            client_event.bind(function)
            return client_event

        return argument_parser_wrapper

    def mark_duplex(
        self,
        server_model: type[BaseModel] | type[BaseModelV2] = None,
        use_event: bool = None,
        include: set[str] = None,
        exclude: set[str] = None,
        exclude_none: bool = None,
    ):
        if is_subtype(server_model, BaseModelV2):
            server_model = v2_model_to_ffs(server_model)

        self._maybe_bind_model(server_model)
        server_kwargs = {
            "include": include,
            "exclude": exclude,
            "exclude_none": exclude_none,
            "use_event": use_event,
        }

        # TODO clearly label: Callable -> Callable & ClientEvent -> DuplexEvent
        def mark_duplex_wrapper(
            value: Callable | ClientEvent,
        ) -> Callable | DuplexEvent:
            if isinstance(value, ClientEvent):
                server_event = self.ServerEvent(server_model, **server_kwargs)
                return self.DuplexEvent(value, server_event)
            return self._update_event_data(
                value,
                dict(server_kwargs, duplex=True, server_model=server_model),
            )

        return mark_duplex_wrapper

    def _marshal_ack_wrapper(
        self,
        ack_model: type[BaseModel] | type[BaseModelV2],
        ack_kwargs: dict,
        function: Callable,
    ) -> Callable:
        if is_subtype(ack_model, BaseModelV2):
            ack_model = v2_model_to_ffs(ack_model)
        return self._update_event_data(function, dict(ack_kwargs, ack_model=ack_model))

    def marshal_ack(
        self,
        ack_model: type[BaseModel] | type[BaseModelV2],
        include: set[str] = None,
        exclude: set[str] = None,
        force_wrap: bool = None,
        exclude_none: bool = None,
    ):
        if is_subtype(ack_model, BaseModelV2):
            ack_model = v2_model_to_ffs(ack_model)
        self._maybe_bind_model(ack_model)
        ack_kwargs = {
            "ack_include": include,
            "ack_exclude": exclude,
            "ack_exclude_none": exclude_none,
            "ack_force_wrap": force_wrap,
        }

        def marshal_ack_wrapper(function: Callable) -> Callable:
            return self._marshal_ack_wrapper(ack_model, ack_kwargs, function)

        return marshal_ack_wrapper

    def force_ack(self, force_wrap: bool = None):
        def force_ack_wrapper(function: Callable) -> Callable:
            return self._update_event_data(
                function, {"force_ack": True, "ack_force_wrap": force_wrap}
            )

        return force_ack_wrapper

    def with_cls(self, klass: type, function: Callable):
        @wraps(function)
        def with_cls_inner(*args, **kwargs):
            return function(klass, *args, **kwargs)

        return with_cls_inner

    def route(self, outer_klass: type | None = None) -> type:
        # TODO mb move data pre- and post-processing from modes to here
        def route_inner(klass: type) -> type:
            for name, value in klass.__dict__.items():
                if isinstance(value, BaseEvent):
                    if isinstance(value, ClientEvent):
                        value.handler = self.with_cls(klass, value.handler)
                    elif isinstance(value, DuplexEvent):
                        value.client_event.handler = self.with_cls(
                            klass, value.client_event.handler
                        )

                    if value.name is None:
                        value.attach_name(
                            name.replace("_", "-") if self.use_kebab_case else name
                        )
                    if self.namespace is not None:
                        value.attach_namespace(self.namespace)
                    self._bind_event(value)

                setattr(klass, name, value)

            return klass

        return route_inner if outer_klass is None else route_inner(outer_klass)


class EventSpace:
    pass
