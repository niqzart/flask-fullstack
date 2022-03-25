from __future__ import annotations

from typing import Type, TypeVar

from flask_restx import Model, Resource
from flask_restx.reqparse import RequestParser

from .interfaces import Identifiable
from .restx import RestXNamespace

t = TypeVar("t", bound="ModBase")


class CRUDLConfig:
    allow_create: bool | None = None
    """ Specifies if the create method should be present
    - True — method will be present, even with an empty `create_parser`
    - False — method will not be present, all other `create_...` arguments will be ignored 
    - None — will be present, only if `create_parser` is provided 
    """
    create_parser: RequestParser | None = None
    """ Parser to be used in the create method """
    create_model: Model | None = None
    """ Model to apply to the returned data of the create method. None defaults to an empty response """

    read_model: Model | None = None
    """ Model to apply to the selected data. If None, read method will not be present """
    read_parser: RequestParser | None = None
    """ Parser to be used in the read method, allows for additional args to be used """
    read_filters: dict | None = None
    """ Additional parameters to add to Base.find_first_by_kwargs method call for the read method """

    update_parser: RequestParser | None = None
    """ Parser to be used in the update method
    It's a good idea to use `store_missing=False` for non-required arguments
    """
    update_model: Model | None = None
    """ Model to apply to the returned data of the update method. None defaults to an empty response """
    update_with_put: bool = True
    """ Defines the HTTP method to be used for updating (True for PUT and False for POST) """

    allow_delete: bool = False
    """ Specifies if the delete method should be present """

    list_model: Model | None = None
    """ Model to apply to the each entry in the selected data. If None, list method will not be present """
    list_page_size: int | None = 50
    """ Sets the page size for pagination. To disable pagination, set it to None """
    list_parser: RequestParser | None = None
    """ Parser to be used in the list method, allows for additional args to be used """
    list_filters: dict | None = None
    """ Additional parameters to add to Base.find_all_by_kwargs method call for the list method """
    list_with_get: bool = True
    """ Defines the HTTP method to be used for listing (True for GET [query args only!] and False for POST) """

    @classmethod
    def common_decorators(cls, function):
        return function

    @classmethod
    def create(cls, creatable: Type[t], **data) -> t | None:
        raise NotImplementedError()

    @classmethod
    def read(cls, identifiable: Type[t], **data) -> t | None:
        raise NotImplementedError()

    @classmethod
    def _update(cls, updatable: t, **data) -> t | None:
        raise NotImplementedError()

    @classmethod
    def update(cls, updatable: Type[t], **data) -> t | None:
        return cls._update(cls.read(updatable, **data), **data)

    @classmethod
    def _delete(cls, deletable: t) -> t | None:
        raise NotImplementedError()

    @classmethod
    def delete(cls, deletable: Type[t], **data) -> None:
        return cls._delete(cls.read(deletable, **data))

    @classmethod
    def list(cls, listable: Type[t], *, offset: int, limit: int, **data) -> list[t]:
        raise NotImplementedError()

    @classmethod
    def make_create_method(cls, namespace: RestXNamespace, creatable: Type[t]):
        if cls.allow_create is not True and cls.create_parser is None:
            return None

        def create_method(**kwargs):
            return cls.create(creatable, **kwargs)

        if cls.create_parser is not None:
            create_method = namespace.argument_parser(cls.create_parser)(create_method)
        if cls.create_model is not None:
            create_method = namespace.marshal_with(cls.create_model)(create_method)

        return cls.common_decorators(create_method)

    @classmethod
    def make_read_method(cls, namespace: RestXNamespace, identifiable: Type[t]):
        if cls.read_model is None:
            return None

        def read_method(**kwargs):
            return cls.read(identifiable, **cls.read_filters, **kwargs)

        if cls.read_parser is not None:
            read_method = namespace.argument_parser(cls.read_parser)(read_method)
        read_method = namespace.marshal_with(cls.read_model)(read_method)

        return cls.common_decorators(read_method)

    @classmethod
    def make_update_method(cls, namespace: RestXNamespace, updatable: Type[t]):
        if cls.update_parser is None:
            return None

        @namespace.argument_parser(cls.update_parser)
        def update_method(**kwargs):
            return cls.update(updatable, **kwargs)

        if cls.update_model is not None:
            update_method = namespace.marshal_with(cls.create_model)(update_method)

        return cls.common_decorators(update_method)

    @classmethod
    def make_delete_method(cls, deletable: Type[t]):
        if not cls.allow_delete:
            return None

        def delete_method(**kwargs):
            return cls.delete(deletable, **kwargs)

        return cls.common_decorators(delete_method)

    @classmethod
    def make_list_method(cls, namespace: RestXNamespace, listable: Type[t]):
        if cls.list_model is None:
            return None

        def list_method(**kwargs):
            return cls.list(listable, **cls.list_filters, **kwargs)

        if cls.list_parser is not None:
            list_method = namespace.argument_parser(cls.list_parser)(list_method)
        if cls.list_page_size is not None:
            list_method = namespace.lister(cls.list_page_size, cls.list_model)(list_method)
        else:
            list_method = namespace.marshal_list_with(cls.list_model)(list_method)

        return cls.common_decorators(list_method)


class RestXNamespaceCRUDL(RestXNamespace):
    def route_crudl(self, identifiable: Type[Identifiable], *urls, **kwargs):
        """  """

        def update_urls(urls, postfix):
            return [u + postfix for u in urls]

        def wrapper(cls: Type[CRUDLConfig]):
            doc = kwargs.pop("doc", None)
            if doc is not None:
                kwargs["route_doc"] = self._build_doc(cls, doc)

            if cls.list_with_get:
                class CLResource(Resource):
                    get = cls.make_list_method(self, identifiable)
                    post = cls.make_create_method(self, identifiable)

                self.add_resource(CLResource, *urls, **kwargs)
            else:
                class CResource(Resource):
                    post = cls.make_create_method(self, identifiable)

                class LResource(Resource):
                    post = cls.make_list_method(self, identifiable)

                self.add_resource(CResource, *urls, **kwargs)
                self.add_resource(LResource, *update_urls(urls, "index/"), **kwargs)

            class RUDResource(Resource):
                get = cls.make_read_method(self, identifiable)
                delete = cls.make_delete_method(identifiable)

            if cls.update_with_put:
                RUDResource.put = cls.make_update_method(self, identifiable)
            else:
                RUDResource.post = cls.make_update_method(self, identifiable)

            self.add_resource(RUDResource, *update_urls(urls, "<int:entry_id>/"), **kwargs)

            return cls

        return wrapper
