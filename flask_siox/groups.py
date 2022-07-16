from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Type, Iterable, Callable

from pydantic import BaseModel

from .events import ClientEvent, ServerEvent, DuplexEvent, BaseEvent
from .utils import kebabify_model


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
            def handler(*args, data=None, **kwargs):
                return function(*args, **event.model.parse_obj(data).dict(), **kwargs)

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

            self._bind_event(BoundEvent(event, event.client_event.model,
                                        handler, getattr(function, "__sio_doc__", None)))
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

    def attach_namespace(self, namespace: str):
        self.namespace = namespace
        for event in self.bound_events:
            event.event.attach_namespace(namespace)
