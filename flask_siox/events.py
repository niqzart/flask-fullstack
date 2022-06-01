from __future__ import annotations

from collections import Callable
from dataclasses import dataclass
from typing import Type

from flask_socketio import emit
from pydantic import BaseModel

from .utils import remove_none


class BaseEvent:  # do not instantiate!
    def __init__(self, name: str = None):
        self.name = None
        if name is not None:
            self.attach_name(name)

    def attach_name(self, name: str):
        raise NotImplementedError

    def create_doc(self, namespace: str, additional_docs: dict = None):
        raise NotImplementedError


class Event(BaseEvent):  # do not instantiate!
    def __init__(self, model: Type[BaseModel], name: str = None, description: str = None):
        super().__init__(name)
        self.model: Type[BaseModel] = model
        self.description: str = description

    def attach_name(self, name: str):
        self.name = name

    def create_doc(self, namespace: str, additional_docs: dict = None):
        model_name: str = getattr(self.model, "name", None) or self.model.__name__
        return remove_none({
            "description": self.description,
            "tags": [{"name": f"namespace-{namespace}"}],
            "message": {"$ref": f"#/components/messages/{model_name}"}
        }, **(additional_docs or {}))


@dataclass()
class ClientEvent(Event):
    def __init__(self, model: Type[BaseModel], name: str = None, description: str = None, handler: Callable = None):
        super().__init__(model, name, description)
        self.handler: Callable = handler

    def parse(self, data: dict):
        return self.model.parse_obj(data).dict()

    def bind(self, function):
        self.handler = lambda data=None: function(**self.parse(data))

    def create_doc(self, namespace: str, additional_docs: dict = None):
        return {"publish": super().create_doc(namespace, additional_docs)}


@dataclass()
class ServerEvent(Event):
    def __init__(self, model: Type[BaseModel], name: str = None, description: str = None,
                 include: set[str] = None, exclude: set[str] = None, exclude_none: bool = True):
        super().__init__(model, name, description)
        self._emit_kwargs = {
            "exclude_none": exclude_none,
            "include": include,
            "exclude": exclude,
            "by_alias": True,
        }
        self.model.Config.allow_population_by_field_name = True

    def _emit(self, data: dict, namespace: str = None, room: str = None, include_self: bool = True):
        return emit(self.name, data, to=room, include_self=include_self, namespace=namespace)

    def emit(self, _room: str = None, _include_self: bool = True, _data: ... = None, _namespace: str = None, **kwargs):
        if _data is None:
            _data: BaseModel = self.model(**kwargs)
        elif not isinstance(_data, self.model):
            _data: BaseModel = self.model.parse_obj(_data)
        return self._emit(_data.dict(**self._emit_kwargs), _namespace, _room, _include_self)

    def create_doc(self, namespace: str, additional_docs: dict = None):
        return {"subscribe": super().create_doc(namespace, additional_docs)}


@dataclass()
class DuplexEvent(BaseEvent):
    def __init__(self, client_event: ClientEvent = None, server_event: ServerEvent = None,
                 name: str = None, description: str = None):
        super().__init__(name)
        self.client_event: ClientEvent = client_event
        self.server_event: ServerEvent = server_event
        self.description: str = description

    @classmethod
    def similar(cls, model: Type[BaseModel], name: str = None, handler: Callable = None,
                include: set[str] = None, exclude: set[str] = None, exclude_none: bool = True):
        return cls(ClientEvent(model, handler=handler),
                   ServerEvent(model, include=include, exclude=exclude, exclude_none=exclude_none), name)

    def attach_name(self, name: str):
        self.name = name
        self.client_event.name = name
        self.server_event.name = name

    def emit(self, _room: str = None, _include_self: bool = True, _data: ... = None, _namespace: str = None, **kwargs):
        return self.server_event.emit(_room, _include_self, _data, _namespace, **kwargs)

    def bind(self, function):
        return self.client_event.bind(function)

    def create_doc(self, namespace: str, additional_docs: dict = None):
        result: dict = self.client_event.create_doc(namespace, additional_docs)
        result.update(self.server_event.create_doc(namespace, additional_docs))
        if self.description is not None:
            result["description"] = self.description
        return result
