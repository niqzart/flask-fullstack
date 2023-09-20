from __future__ import annotations

from typing import Any

from pydantic_marshals.contains import assert_contains
from pydantic_marshals.contains.type_aliases import TypeChecker
from werkzeug.test import TestResponse


def check_code(
    response: TestResponse,
    status_code: int = 200,
    get_json: bool = True,
) -> dict | list | TestResponse:
    assert response.status_code == status_code, response.get_json()
    return response.get_json() if get_json else response


def check_response(
    response: TestResponse,
    expected_status: int = 200,
    expected_data: Any | None = None,
    expected_text: str | None = None,
    expected_json: TypeChecker = None,
    expected_headers: TypeChecker = None,
    get_json: bool = True,
) -> None | dict | list | TestResponse:
    assert response.status_code == expected_status, response.get_json()
    if expected_headers is not None:
        assert_contains(dict(response.headers.items()), expected_headers)

    if expected_data is not None:
        assert response.data == expected_data
    if expected_text is not None:
        assert response.text == expected_text
    if expected_json is not None:
        real_json = response.get_json(silent=True)
        assert_contains(real_json, expected_json)

    return response.get_json(silent=True) if get_json else response
