from __future__ import annotations

from collections import OrderedDict
from typing import Callable
from logging import Filter, getLogger

from flask_socketio import Namespace as _Namespace, SocketIO as _SocketIO

from .groups import EventGroup


class Namespace(_Namespace):
    def __init__(self, namespace: str = None, use_kebab_case: bool = False):
        super().__init__(namespace)
        self.doc_channels = OrderedDict()
        self.doc_messages = OrderedDict()
        self.use_kebab_case = use_kebab_case

    def attach_event_group(self, event_group: EventGroup):
        event_group.attach_namespace(self.namespace)
        self.doc_channels.update(event_group.extract_doc_channels())
        self.doc_messages.update(event_group.extract_doc_messages())
        for name, handler in event_group.extract_handlers():
            if self.use_kebab_case:
                name = name.replace("-", "_")
            setattr(self, f"on_{name}", handler)

    def on_event(self, name: str):
        def on_event_wrapper(function: Callable[[...], None]):
            setattr(self, f"on_{name}", function)

        return on_event_wrapper

    def on_connect(self, function: Callable[[...], None] | None = None):
        if function is None:
            def on_connect_wrapper(function: Callable[[...], None]):
                setattr(self, f"on_connect", function)

            return on_connect_wrapper

        setattr(self, f"on_connect", function)

    def on_disconnect(self, function: Callable[[...], None] = None):
        if function is None:
            def on_disconnect_wrapper(function: Callable[[...], None]):
                setattr(self, f"on_disconnect", function)

            return on_disconnect_wrapper

        setattr(self, f"on_disconnect", function)


class NoPingPongFilter(Filter):
    def filter(self, record):
        return not ("Received packet PONG" in record.getMessage() or "Sending packet PING" in record.getMessage())


class SocketIO(_SocketIO):
    def __init__(self, app=None, title: str = "SIO", version: str = "1.0.0", doc_path: str = "/sio-doc/",
                 remove_ping_pong_logs: bool = False, **kwargs):
        self.async_api = {"asyncapi": "2.2.0", "info": {"title": title, "version": version},
                          "channels": OrderedDict(), "components": {"messages": OrderedDict()}}
        self.doc_path = doc_path
        if remove_ping_pong_logs:
            getLogger("engineio.server").addFilter(NoPingPongFilter())
        super(SocketIO, self).__init__(app, **kwargs)

    def docs(self):
        return self.async_api

    def init_app(self, app, **kwargs):
        app.config["JSON_SORT_KEYS"] = False  # TODO kinda bad for a library

        @app.route(self.doc_path)
        def documentation():
            return self.docs()

        return super(SocketIO, self).init_app(app, **kwargs)

    def on_namespace(self, namespace_handler):
        if isinstance(namespace_handler, Namespace):
            self.async_api["channels"].update(namespace_handler.doc_channels)
            self.async_api["components"]["messages"].update(namespace_handler.doc_messages)
        return super(SocketIO, self).on_namespace(namespace_handler)
