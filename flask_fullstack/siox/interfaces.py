from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterable

from pydantic.v1 import BaseModel

from .events import BaseEvent, ClientEvent, DuplexEvent, ServerEvent  # noqa: F401


class EventGroupBase:
    ClientEvent: type[ClientEvent] = ClientEvent
    ServerEvent: type[ServerEvent] = ServerEvent  # noqa: F811
    DuplexEvent: type[DuplexEvent] = DuplexEvent

    def __init__(self, namespace: str = None, use_kebab_case: bool = False):
        self.use_kebab_case: bool = use_kebab_case
        self.namespace: str | None = namespace
        self.bound_models: list[type[BaseModel]] = []
        self.bound_events: list[BaseEvent] = []

    def _bind_event(self, event: BaseEvent):
        self.bound_events.append(event)

    def _get_model_name(self, bound_model: type[BaseModel]):
        return bound_model.__name__

    def _get_model_schema(self, bound_model: type[BaseModel]):
        return {
            "payload": bound_model.schema(ref_template="#/components/messages/{model}")
        }

    def _bind_model(self, bound_model: type[BaseModel]):
        self.bound_models.append(bound_model)

    def extract_doc_messages(self) -> OrderedDict[str, ...]:
        return OrderedDict(
            (self._get_model_name(bound_model), self._get_model_schema(bound_model))
            for bound_model in self.bound_models
        )

    def _get_event_name(self, event: BaseEvent):
        if self.use_kebab_case:
            return event.name.replace("_", "-")
        return event.name

    def _create_doc(self, event: BaseEvent):
        return event.create_doc(self.namespace or "/")

    def extract_doc_channels(self) -> OrderedDict[str, ...]:
        return OrderedDict(
            (self._get_event_name(event), self._create_doc(event))
            for event in self.bound_events
        )

    def extract_handlers(self) -> Iterable[tuple[str, Callable]]:
        for event in self.bound_events:
            if isinstance(event, ClientEvent):
                yield event.name, event
            elif isinstance(event, DuplexEvent):
                yield event.client_event.name, event.client_event

    def attach_namespace(self, namespace: str):
        for event in self.bound_events:
            event.attach_namespace(namespace)
