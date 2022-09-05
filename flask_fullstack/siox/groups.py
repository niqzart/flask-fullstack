from __future__ import annotations

from typing import Type, Callable

from pydantic import BaseModel

from .events import ClientEvent, ServerEvent, DuplexEvent
from .interfaces import EventGroupBase
from .utils import kebabify_model


class EventGroup(EventGroupBase):  # DEPRECATED
    @staticmethod
    def _kebabify(name: str | None, model: Type[BaseModel]) -> str | None:
        kebabify_model(model)
        if name is None:
            return None
        return name.replace("_", "-")

    def bind_pub_full(self, event: ClientEvent) -> Callable[[Callable], ClientEvent]:
        if self.namespace is not None:
            event.attach_namespace(self.namespace)
        kebabify_model(event.model)
        self._bind_model(event.model)

        def bind_pub_wrapper(function) -> ClientEvent:
            def handler(*args, data=None, **kwargs):
                return function(*args, **event.model.parse_obj(data).dict(), **kwargs)

            event.handler = handler
            self._bind_event(event)
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
        self._bind_event(event)
        self._bind_model(event.model)
        return event

    def bind_sub(self, model: Type[BaseModel], *, description: str = None, name: str = None) -> ServerEvent:
        if self.use_kebab_case and name is not None:
            name = name.replace("_", "-")
        return self.bind_sub_full(self.ServerEvent(model, name, description))

    def bind_dup_full(self, event: DuplexEvent, same_model: bool = True,
                      use_event: bool = None) -> Callable[[Callable], DuplexEvent]:
        if use_event is None:
            use_event = False
        if self.namespace is not None:
            event.attach_namespace(self.namespace)
        kebabify_model(event.client_event.model)
        kebabify_model(event.server_event.model)
        self._bind_model(event.client_event.model)
        if not same_model:
            self._bind_model(event.server_event.model)

        def bind_dup_wrapper(function) -> DuplexEvent:
            def handler(*args, **kwargs):
                data = args[-1]
                args = list(args[:-1])
                if use_event:
                    args.append(event)
                return function(*args, **event.client_event.model.parse_obj(data).dict(), **kwargs)

            event.client_event.handler = handler
            self._bind_event(event)
            return event

        return bind_dup_wrapper

    def bind_dup(self, model: Type[BaseModel], server_model: Type[BaseModel] = None,
                 ack_model: Type[BaseModel] = None, *, description: str = None,
                 name: str = None, use_event: bool = None) -> Callable[[Callable], DuplexEvent]:
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
