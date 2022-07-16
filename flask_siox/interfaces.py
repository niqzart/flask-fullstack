from __future__ import annotations

from collections import OrderedDict
from typing import Type, Iterable, Callable

from pydantic import BaseModel

from .events import ClientEvent, ServerEvent, DuplexEvent


class EventGroupBase:
    ClientEvent: Type[ClientEvent] = ClientEvent
    ServerEvent: Type[ServerEvent] = ServerEvent
    DuplexEvent: Type[DuplexEvent] = DuplexEvent

    def __init__(self, namespace: str = None, use_kebab_case: bool = False):
        self.use_kebab_case: bool = use_kebab_case
        self.namespace: str | None = namespace
        self.bound_models: list[Type[BaseModel]] = []

    @staticmethod
    def _get_model_name(bound_model: Type[BaseModel]):
        return bound_model.__name__

    @staticmethod
    def _get_model_schema(bound_model: Type[BaseModel]):
        return {"payload": bound_model.schema(ref_template="#/components/messages/{model}")}

    def _bind_model(self, bound_model: Type[BaseModel]):
        self.bound_models.append(bound_model)

    def extract_doc_messages(self) -> OrderedDict[str, ...]:
        return OrderedDict((self._get_model_name(bound_model), self._get_model_schema(bound_model))
                           for bound_model in self.bound_models)

    def extract_doc_channels(self) -> OrderedDict[str, ...]:
        raise NotImplementedError()

    def extract_handlers(self) -> Iterable[tuple[str, Callable]]:
        raise NotImplementedError()

    def attach_namespace(self, namespace: str):
        raise NotImplementedError()
