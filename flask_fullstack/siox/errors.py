from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EventException(Exception):
    code: int
    message: str
    data: Any = None
    critical: bool = False
