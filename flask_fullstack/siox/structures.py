from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from logging import Filter, getLogger

from flask_restx import Model
from flask_socketio import Namespace as _Namespace, SocketIO as _SocketIO, disconnect

from .errors import EventException
from .interfaces import EventGroupBase
from ..utils import render_packed, restx_model_to_message


class Namespace(_Namespace):
    def __init__(self, namespace: str = None, use_kebab_case: bool = False):
        super().__init__(namespace)
        self.doc_channels = OrderedDict()
        self.doc_messages = OrderedDict()
        self.use_kebab_case = use_kebab_case

    def on_event(self, name: str):
        def on_event_wrapper(function: Callable[[...], None]):
            setattr(self, f"on_{name}", function)

        return on_event_wrapper

    def on_connect(self, function: Callable[[...], None] | None = None):
        def on_connect_wrapper(function: Callable[[...], None]):
            self.on_connect = function

        if function is None:
            return on_connect_wrapper
        return on_connect_wrapper(function)

    def on_disconnect(self, function: Callable[[...], None] = None):
        def on_disconnect_wrapper(function: Callable[[...], None]):
            self.on_disconnect = function

        if function is None:
            return on_disconnect_wrapper
        return on_disconnect_wrapper(function)

    def attach_event_group(self, event_group: EventGroupBase):
        event_group.attach_namespace(self.namespace)
        self.doc_channels.update(event_group.extract_doc_channels())
        self.doc_messages.update(event_group.extract_doc_messages())
        for name, handler in event_group.extract_handlers():
            self.on_event(name)(handler)

    def handle_exception(
        self,
        data: dict | list | str | int | None = None,
        code: int | None = None,
        message: str | None = None,
    ) -> dict | None:
        return render_packed(data=data, code=code, message=message)

    def trigger_event(self, event, *args):
        try:
            return super().trigger_event(event, *args)
        except EventException as e:
            if e.critical:
                disconnect()
            return self.handle_exception(code=e.code, message=e.message, data=e.data)


class NoPingPongFilter(Filter):
    def filter(self, record):
        return not (
            "Received packet PONG" in record.getMessage()
            or "Sending packet PING" in record.getMessage()
        )


class SocketIO(_SocketIO):
    default_namespace_class: type[Namespace] = Namespace

    def __init__(
        self,
        app=None,
        title: str = "SIO",
        version: str = "1.0.0",
        doc_path: str = "/sio-doc/",
        remove_ping_pong_logs: bool = False,
        use_kebab_case: bool = False,
        namespace_class: type[Namespace] = None,
        restx_models: dict[str, Model] = None,  # TODO get rid of restx
        **kwargs,
    ):
        self.doc_path = doc_path
        self.use_kebab_case = use_kebab_case
        self.namespace_class = (
            self.default_namespace_class if namespace_class is None else namespace_class
        )

        self.async_api = {
            "asyncapi": "2.2.0",
            "info": {"title": title, "version": version},
            "channels": OrderedDict(),
            "components": {
                "messages": OrderedDict(
                    (name, restx_model_to_message(name, model))
                    for name, model in (restx_models or {}).items()
                )
            },
        }

        if remove_ping_pong_logs:
            getLogger("engineio.server").addFilter(NoPingPongFilter())

        super().__init__(app, **kwargs)

    def docs(self):
        return self.async_api

    def init_app(self, app, **kwargs):
        app.config["JSON_SORT_KEYS"] = False  # TODO kinda bad for a library

        @app.route(self.doc_path)
        def documentation():
            return self.docs()

        return super().init_app(app, **kwargs)

    def on_namespace(self, namespace_handler):
        if isinstance(namespace_handler, Namespace):
            self.async_api["channels"].update(namespace_handler.doc_channels)
            self.async_api["components"]["messages"].update(
                namespace_handler.doc_messages
            )
        return super().on_namespace(namespace_handler)

    def _add_namespace(self, namespace: Namespace, *event_groups: EventGroupBase):
        for event_group in event_groups:
            namespace.attach_event_group(event_group)
        self.on_namespace(namespace)

    def add_namespace(self, name: str = None, *event_groups: EventGroupBase, **_):
        self._add_namespace(
            self.namespace_class(name, self.use_kebab_case),
            *event_groups,
        )
