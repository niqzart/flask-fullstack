from __future__ import annotations

from flask import Flask
from flask.testing import FlaskClient
from flask_socketio.test_client import SocketIOTestClient as _SocketIOTestClient
from pydantic_marshals.contains import assert_contains
from pydantic_marshals.contains.type_aliases import TypeChecker

from flask_fullstack.siox.structures import SocketIO
from flask_fullstack.utils.kebabs import dekebabify, kebabify, kebabify_string


class SocketIOTestClient(_SocketIOTestClient):
    def __init__(self, flask_client: FlaskClient):
        app: Flask = flask_client.application
        socketio: SocketIO = app.extensions.get("socketio")
        if socketio is None:
            raise EnvironmentError("Socketio not initialized")
        super().__init__(app, socketio, flask_test_client=flask_client)

    def count_received(self):
        """Counts received server events in queue without modifying the queue"""
        return len(self.queue[self.eio_sid])

    def assert_nop(self):
        """Asserts that there are no events in queue"""
        assert self.count_received() == 0

    def assert_emit_ack(
        self,
        event_name: str,
        data: dict,
        *args,
        get_data: bool = True,
        with_nop: bool = True,
        expected_ack: dict = None,
        expected_code: int = 200,
        expected_message: str | None = None,
        expected_data: TypeChecker = None,
        **kwargs,
    ) -> ...:
        """
        Emits an event and compares the contents of its ack against provided data (with asserts)

        :param event_name: a client event name
        :param data: data to send with the event
        :param get_data: (default: True) set True to only ack's data, False for the full ack
        :param with_nop: (default: True) set True to additionally assert that there are no events in queue
        :param expected_ack: (default: None) the full ack object in the ack (None for no check)
        :param expected_code: (default: 200) the code to expect in the ack
        :param expected_message: (default: None) the message to expect in the ack (None for no check)
        :param expected_data: (default: None) the data to expect in the ack (None for no check)
        :param args: arguments to pass to normal emit
        :param kwargs: kwargs to pass to normal emit
        :return: full ack (dict) or ack's data (likely dict)
        """
        kwargs["callback"] = True
        event_name = kebabify_string(event_name)
        ack = dekebabify(self.emit(event_name, kebabify(data), *args, **kwargs))

        if with_nop:
            self.assert_nop()

        assert isinstance(ack, dict), ack
        if expected_ack is not None:
            assert_contains(ack, expected_ack)

        assert ack.get("code") == expected_code, ack
        if expected_message is not None:
            assert ack.get("message") == expected_message
        if expected_data is not None:
            assert_contains(ack.get("data"), expected_data)

        if get_data:
            return ack.get("data")
        return ack

    def assert_emit_success(
        self,
        event_name: str,
        *args,
        code: int = 200,
        message: str | None = "Success",
        with_nop: bool = True,
        **kwargs,
    ):
        """
        Emits an event and compares the contents of its ack against provided data (with asserts).
        Defaults are set to compare with the standard success response from `.force_ack` decorator

        :param event_name: a client event name
        :param code: (default: 200) the code to expect in the ack
        :param message: (default: "Success") the message to expect in the ack (None for no check)
        :param with_nop: (default: True) set True to additionally assert that there are no events in queue
        :param args: arguments to pass to normal emit
        :param kwargs: kwargs to pass to normal emit
        """
        assert (
            self.assert_emit_ack(
                event_name,
                *args,
                expected_code=code,
                expected_message=message,
                with_nop=with_nop,
                **kwargs,
            )
            is None
        )

    def assert_received(
        self, event_name: str, expected_data: TypeChecker, *, pop: bool = True
    ) -> dict:
        """
        Checks if the socket received some event with some data
        and optionally removes it from the queue

        :param event_name: a server event name
        :param expected_data: data, that the event should have
        :param pop: (default: True) if True, the event is removed from queue
        :return: received event's data
        """
        expected_data = kebabify(expected_data)
        event_name = kebabify_string(event_name)
        result: list[tuple[..., int]] = [
            (pkt, i)
            for i, pkt in enumerate(self.queue[self.eio_sid])
            if pkt["name"] == event_name
        ]

        assert len(result) == 1
        pkt, i = result[0]

        pkt_args = pkt.get("args")
        assert isinstance(pkt_args, list)
        assert len(pkt_args) == 1

        event_data = pkt["args"][0]
        assert_contains(event_data, expected_data)

        if pop:
            self.queue[self.eio_sid].pop(i)

        return event_data

    def assert_only_received(self, event_name: str, data: TypeChecker) -> dict:
        """
        Same as `.assert_received`, but also checks if that's the only received event.
        Checks if the socket received some event with some data and removes it from the queue

        :param event_name: a server event name
        :param data: data, that the event should have
        :return: received event's data
        """
        assert self.count_received() == 1
        return self.assert_received(event_name, data)

    @staticmethod
    def assert_broadcast(
        event_name: str,
        data: TypeChecker,
        *clients: SocketIOTestClient,
        pop: bool = True,
    ) -> None:
        """
        Same as `.assert_received`, but for bulk checks.
        For each socket it checks if that socket received some event
        with some data and optionally removes it from the queue

        :param event_name: a server event name
        :param data: data, that the event should have
        :param pop: (default: True) if True, the event is removed from queue
        :return: received event's data
        """
        for client in clients:
            client.assert_received(event_name, data, pop=pop)

    @staticmethod
    def assert_bulk_nop(*clients: SocketIOTestClient) -> None:
        """Asserts that there is no events in queue for all clients"""
        for client in clients:
            client.assert_nop()
