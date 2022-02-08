from abc import ABCMeta
from typing import Type, Union

from flask_fullstack import Identifiable, get_or_pop


class AbstractAbortMixin:
    def abort(self, error_code: Union[int, str], description: str, *, critical: bool = False, **kwargs):
        raise NotImplementedError


class DatabaseSearcherMixin(AbstractAbortMixin, metaclass=ABCMeta):
    def _database_searcher(self, identifiable: Type[Identifiable], check_only: bool, no_id: bool,
                           use_session: bool, error_code: int, callback, args, kwargs, *,
                           input_field_name: Union[str, None] = None, result_field_name: Union[str, None] = None):
        if input_field_name is None:
            input_field_name = identifiable.__name__.lower() + "_id"
        if result_field_name is None:
            result_field_name = identifiable.__name__.lower()
        session = get_or_pop(kwargs, "session", use_session)
        target_id: int = get_or_pop(kwargs, input_field_name, check_only and not no_id)
        if (result := identifiable.find_by_id(session, target_id)) is None:
            self.abort(error_code, identifiable.not_found_text)
        else:
            if not check_only:
                kwargs[result_field_name] = result
            return callback(*args, **kwargs)
