from __future__ import annotations

from typing import Sequence


def unpack_params(result: Sequence) -> tuple[dict | None, int | None, str | None]:
    code: int | None = None
    message: str | None = None

    if len(result) == 2:
        data, second = result
        if isinstance(second, int):
            code = second
        elif isinstance(second, str):
            message = second
    elif len(result) == 3:
        data, code, message = result

    if isinstance(data, str) and message is None:
        return None, code, data

    return data, code, message
