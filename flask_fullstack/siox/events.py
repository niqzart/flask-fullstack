from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import wraps

from flask_socketio import emit
from pydantic.v1 import BaseModel, ValidationError

from .errors import EventException
from ..utils import remove_none, render_model, render_packed, unpack_params


class BaseEvent:  # do not instantiate!
    def __init__(
        self,
        name: str = None,
        namespace: str = None,
    ):
        self.name = None
        self.namespace = namespace
        if name is not None:
            self.attach_name(name)

    def attach_name(self, name: str):
        raise NotImplementedError

    def attach_namespace(self, namespace: str):
        raise NotImplementedError

    def create_doc(self, namespace: str):
        raise NotImplementedError


class Event(BaseEvent):  # do not instantiate!
    def __init__(
        self,
        model: type[BaseModel],
        namespace: str = None,
        name: str = None,
        description: str = None,
    ):
        super().__init__(name, namespace)
        self.model: type[BaseModel] = model
        self.description: str = description

    def attach_name(self, name: str):
        self.name = name

    def attach_namespace(self, namespace: str):
        self.namespace = namespace

    def create_doc(self, namespace: str = None):
        model_name: str = getattr(self.model, "name", None) or self.model.__name__
        if namespace is None:
            namespace = self.namespace
        return remove_none(
            {
                "description": self.description,
                "tags": [{"name": f"namespace-{namespace}"}]
                if namespace is not None
                else None,
                "message": {"$ref": f"#/components/messages/{model_name}"},
            }
        )


@dataclass()
class ClientEvent(Event):
    def __init__(
        self,
        model: type[BaseModel],
        ack_model: type[BaseModel] = None,
        namespace: str = None,
        name: str = None,
        description: str = None,
        handler: Callable = None,
        include: set[str] = None,
        exclude: set[str] = None,
        exclude_none: bool = None,
        force_wrap: bool = None,
        force_ack: bool = None,
        additional_models: list[dict] = None,
    ):
        super().__init__(model, namespace, name, description)
        self._ack_kwargs = {
            "exclude_none": exclude_none is not False,
            "include": include,
            "exclude": exclude,
            "by_alias": True,
        }
        self.handler: Callable[[dict | None], dict] = handler
        self.ack_model: type[BaseModel] = ack_model
        self.force_wrap: bool = force_wrap is True
        self.forced_ack: bool = force_ack is True and ack_model is None
        self.additional_models: list[dict] = additional_models or []

    def parse(self, data: dict):
        return self.model.parse_obj(data).dict()

    def _force_wrap(self, result) -> dict:
        return {"data": result}

    def _render_model(self, result) -> dict | str | int | None:
        if self.forced_ack:
            return result
        return render_model(self.ack_model, result, **self._ack_kwargs)

    def _ack_response(self, result) -> dict:
        if isinstance(result, Sequence) and not isinstance(result, str):
            result, code, message = unpack_params(result)
            return render_packed(self._render_model(result), code, message)

        result = self._render_model(result)
        return self._force_wrap(result) if self.force_wrap else result

    def _handler(self, function: Callable[..., dict]):
        if self.forced_ack or self.ack_model is not None:

            @wraps(function)
            def _handler_inner(*args, **kwargs):
                return self._ack_response(function(*args, **kwargs))

            return _handler_inner
        return function

    def bind(self, function):
        self.handler = self._handler(function)

    def __call__(self, data=None):
        try:
            kwargs = self.parse(data)
        except ValidationError as e:
            raise EventException(code=400, message="Validation failed", data=e.errors())
        return self.handler(**kwargs)

    def attach_ack(
        self,
        ack_model: type[BaseModel],
        include: set[str] = None,
        exclude: set[str] = None,
        force_wrap: bool = None,
        exclude_none: bool = None,
    ) -> None:
        self._ack_kwargs = {
            "exclude_none": exclude_none is not False,
            "include": include,
            "exclude": exclude,
            "by_alias": True,
        }
        self.ack_model: type[BaseModel] = ack_model
        self.force_wrap: bool = force_wrap is True
        if self.handler is not None:

            @wraps(self.handler)
            def _handler(*args, **kwargs):
                return self._ack_response(self.handler(*args, **kwargs))

            self.handler = _handler

    def ack_model_doc(self):
        if self.forced_ack:
            data = {"type": ["boolean", "integer", "string"]}
        else:
            model_name: str = (
                getattr(self.ack_model, "name", None) or self.ack_model.__name__
            )
            data = {"$ref": f"#/components/messages/{model_name}/payload"}
        return {
            "name": f"{self.name}-ack",
            "payload": {
                "type": "object",
                "required": ["code"] if self.forced_ack else ["code", "data"],
                "properties": {
                    "code": {"type": "integer"},
                    "message": {"type": "string"},
                    "data": data,
                },
            },
        }

    def create_doc(self, namespace: str = None):
        result = super().create_doc(namespace)
        models = [result["message"]] + [
            {"name": f"{self.name}-error-{i}", "payload": model}
            for i, model in enumerate(self.additional_models)
        ]

        if self.ack_model or self.forced_ack:
            models.insert(1, self.ack_model_doc())

        result["message"] = {"oneOf": models}
        return {"publish": result}


@dataclass()
class ServerEvent(Event):
    def __init__(
        self,
        model: type[BaseModel],
        namespace: str = None,
        name: str = None,
        description: str = None,
        include: set[str] = None,
        exclude: set[str] = None,
        exclude_none: bool = None,
    ):
        super().__init__(model, namespace, name, description)
        self._emit_kwargs = {
            "exclude_none": exclude_none is not False,
            "include": include,
            "exclude": exclude,
            "by_alias": True,
        }
        self.model.Config.allow_population_by_field_name = True

    def _emit(
        self,
        data: dict,
        namespace: str = None,
        room: str = None,
        include_self: bool = True,
        broadcast: bool = False,
    ):
        return emit(
            self.name,
            data,
            to=room,
            include_self=include_self,
            namespace=namespace,
            broadcast=broadcast,
        )

    def emit(
        self,
        _room: str = None,
        _include_self: bool = True,
        _broadcast: bool = True,
        _data: ... = None,
        _namespace: str = None,
        **kwargs,
    ):
        if _data is None:
            _data: BaseModel = self.model(**kwargs)
        return self._emit(
            render_model(self.model, _data, **self._emit_kwargs),
            _namespace,
            _room,
            _include_self,
            _broadcast,
        )

    def create_doc(self, namespace: str = None):
        return {"subscribe": super().create_doc(namespace)}


@dataclass()
class DuplexEvent(BaseEvent):
    def __init__(
        self,
        client_event: ClientEvent = None,
        server_event: ServerEvent = None,
        use_event: bool = None,
        namespace: str = None,
        name: str = None,
        description: str = None,
    ):
        super().__init__(name, namespace)
        self.client_event: ClientEvent = client_event
        self.server_event: ServerEvent = server_event
        self.description: str = description
        self.use_event: bool = bool(use_event)

    @classmethod
    def similar(
        cls,
        model: type[BaseModel],
        ack_model: type[BaseModel] = None,
        use_event: bool = None,
        name: str = None,
        description: str = None,
        namespace: str = None,
        handler: Callable = None,
        include: set[str] = None,
        exclude: set[str] = None,
        exclude_none: bool = True,
        ack_include: set[str] = None,
        ack_exclude: set[str] = None,
        ack_exclude_none: bool = True,
        ack_force_wrap: bool = None,
        ack_force: bool = None,
        additional_models: list[dict] = None,
    ):
        return cls(
            ClientEvent(
                model=model,
                ack_model=ack_model,
                namespace=namespace,
                name=name,
                description=description,
                handler=handler,
                include=ack_include,
                exclude=ack_exclude,
                exclude_none=ack_exclude_none,
                force_wrap=ack_force_wrap,
                force_ack=ack_force,
                additional_models=additional_models,
            ),
            ServerEvent(
                model=model,
                name=name,
                namespace=namespace,
                description=description,
                include=include,
                exclude=exclude,
                exclude_none=exclude_none,
            ),
            use_event=use_event,
            namespace=namespace,
            name=name,
            description=description,
        )

    def attach_name(self, name: str):
        self.name = name
        self.client_event.name = name
        self.server_event.name = name

    def attach_namespace(self, namespace: str):
        self.namespace = namespace
        self.client_event.namespace = namespace
        self.server_event.namespace = namespace

    def emit(
        self,
        _room: str = None,
        _include_self: bool = True,
        _broadcast: bool = True,
        _data: ... = None,
        _namespace: str = None,
        **kwargs,
    ):
        return self.server_event.emit(
            _room,
            _include_self,
            _broadcast,
            _data,
            _namespace,
            **kwargs,
        )

    def bind(self, function: Callable[..., dict]):
        if self.use_event:

            @wraps(function)
            def duplex_handler(*args, **kwargs):
                return function(*args, event=self, **kwargs)

            return self.client_event.bind(duplex_handler)
        return self.client_event.bind(function)

    def __call__(self, data=None):
        return self.client_event(data)

    def create_doc(self, namespace: str = None):
        result: dict = self.client_event.create_doc(namespace)
        result.update(self.server_event.create_doc(namespace))
        if self.description is not None:
            result["description"] = self.description
        return result
