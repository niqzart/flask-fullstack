from abc import ABCMeta

from .mixins import DatabaseSearcherMixin
from ..flask_siox import EventGroup as _EventGroup


class EventGroup(_EventGroup, DatabaseSearcherMixin, metaclass=ABCMeta):
    pass
