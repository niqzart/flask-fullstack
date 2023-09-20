from __future__ import annotations

from typing import Any, Iterator, Protocol, Type, Union

from flask.testing import FlaskClient as _FlaskClient
from werkzeug.test import TestResponse

from flask_fullstack.utils.contains import TypeChecker
from flask_fullstack.utils.pytest import check_response

HeaderChecker = dict[str, Union[str, Type[str], None]]


class OpenProtocol(Protocol):
    def __call__(
        self,
        path: str = "/",
        *args: Any,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
        expected_status: int = 200,
        expected_data: Any | None = None,
        expected_text: str | None = None,
        expected_json: TypeChecker | None = None,
        expected_headers: HeaderChecker | None = None,
        get_json: bool = True,
        **kwargs: Any,
    ) -> None | dict | list | TestResponse:  # TODO mb overload /w return types
        pass


class FlaskTestClient(_FlaskClient):
    head: OpenProtocol
    post: OpenProtocol
    get: OpenProtocol
    put: OpenProtocol
    patch: OpenProtocol
    delete: OpenProtocol
    options: OpenProtocol
    trace: OpenProtocol

    def open(  # noqa: A003
        self,
        *args: Any,
        expected_status: int = 200,
        expected_data: Any | None = None,
        expected_text: str | None = None,
        expected_json: TypeChecker | None = None,
        expected_headers: HeaderChecker | None = None,
        get_json: bool = True,
        **kwargs: Any,
    ) -> None | dict | list | TestResponse:
        # TODO redirects are kinda broken with this
        return check_response(
            super().open(*args, **kwargs),
            expected_status=expected_status,
            expected_data=expected_data,
            expected_text=expected_text,
            expected_json=expected_json,
            expected_headers=expected_headers,
            get_json=get_json,
        )

    def get_file(
        self,
        *args: Any,
        expected_status: int = 200,
        expected_data: Any,
        expected_headers: HeaderChecker | None = None,
        get_json: bool = False,
        **kwargs: Any,
    ) -> None | dict | list | TestResponse:
        return self.open(
            *args,
            expected_status=expected_status,
            expected_data=expected_data,
            expected_headers=expected_headers,
            get_json=get_json,
            **kwargs,
        )

    def paginate(
        self,
        *args: Any,
        json: Any = None,
        method: str = "GET",
        expected_status: int = 200,
        **kwargs: Any,
    ) -> Iterator[dict]:
        if json is None:
            json = {}

        received: int = 0
        has_next: bool = True

        while has_next:
            json["offset"] = received
            response: dict = self.open(
                *args,
                json=json,
                method=method,
                expected_status=expected_status,
                expected_json={"results": list},
                **kwargs,
            )

            yield from response["results"]
            received += len(response["results"])
            has_next = response.get("has-next", response.get("has_next"))
            assert isinstance(has_next, bool)
