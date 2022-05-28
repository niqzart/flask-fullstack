from __future__ import annotations

from abc import ABC
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Type, Sequence, Union, get_type_hints, Callable, TypeVar, ForwardRef

from flask_restx import Model as _Model, Namespace
from flask_restx.fields import (Boolean as BooleanField, Integer as IntegerField, Float as FloatField,
                                String as StringField, Raw as RawField, Nested as NestedField, List as ListField)
from flask_restx.reqparse import RequestParser
from pydantic import BaseModel
from pydantic.fields import ModelField
from sqlalchemy import Column, Sequence, Float
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.types import Boolean, Integer, String, JSON, DateTime, Enum

from .sqlalchemy import JSONWithModel
from .utils import TypeEnum, Nameable


class EnumField(StringField):
    def format(self, value: TypeEnum) -> str:
        return value.to_string()


class DateTimeField(StringField):
    def format(self, value: datetime) -> str:
        return value.isoformat()


class JSONLoadableField(RawField):
    def format(self, value):
        return value


# class ConfigurableField:
#     @classmethod
#     def create(cls, column: Column, column_type: Union[Type[TypeEngine], TypeEngine],
#                default=None) -> Union[RawField, Type[RawField]]:
#         raise NotImplementedError


class JSONWithModelField:  # (ConfigurableField):
    # @classmethod
    # def create(cls, column: Column, *_) -> RawField:
    #     field = NestedField(flask_restx_has_bad_design.model(column.type.model_name, column.type.model))
    #     if column.type.as_list:
    #         return ListField(field)
    #     return field
    pass


# class JSONWithSchemaField(ConfigurableField):
#     @classmethod
#     def create(cls, column: Column, column_type: JSONWithSchema, default=None) -> Type[JSONLoadableField]:
#         class JSONField(JSONLoadableField):
#             __schema_type__ = column.type.schema_type
#             __schema_format__ = column.type.schema_format  # doesn't work!
#             __schema_example__ = column.type.schema_example or default
#
#         return JSONField


type_to_field: dict[type, Type[RawField]] = {
    bool: BooleanField,
    int: IntegerField,
    float: FloatField,
    str: StringField,
    JSON: JSONLoadableField,
    datetime: DateTimeField,
}

column_to_field: dict[Type[TypeEngine], Type[RawField]] = {
    JSONWithModel: JSONWithModelField,
    JSON: JSONLoadableField,
    DateTime: DateTimeField,
    Enum: EnumField,
    Boolean: BooleanField,
    Integer: IntegerField,
    Float: FloatField,
    String: StringField,
}

column_to_type: dict[Type[TypeEngine], type] = {
    DateTime: datetime,
    Boolean: bool,
    Integer: int,
    Float: float,
    String: str,
}


def pydantic_field_to_kwargs(field: ModelField) -> dict[str, ...]:
    return {"default": field.default, "required": field.required}


def sqlalchemy_column_to_kwargs(column: Column) -> dict[str, ...] | None:
    result: dict[str, ...] = {"default": column.default, "required": not column.nullable and column.default is None}

    for supported_type, type_ in column_to_field.items():
        if isinstance(column.type, supported_type):
            result["type"] = type_
            return result

    if isinstance(column.type, Enum):
        result["type"] = str
        # result["choices"] = column.type  # TODO support for enums with a renewed TypeEnum field
        return result


flask_restx_has_bad_design: Namespace = Namespace("this-is-dumb")


def move_field_attribute(root_name: str, field_name: str, field_def: Type[RawField] | RawField):
    attribute_name: str = f"{root_name}.{field_name}"
    if isinstance(field_def, type):
        return field_def(attribute=attribute_name)
    field_def.attribute = attribute_name
    return field_def


def create_fields(column: Column, name: str, use_defaults: bool = False, flatten_jsons: bool = False,
                  required: bool = None, attribute: str = None) -> dict[str, ...]:
    if not use_defaults or column.default is None or column.nullable or isinstance(column.default, Sequence):
        default = None
        required = required or not column.nullable
    else:
        default = column.default.arg
        required = required or False

    for supported_type, field_type in column_to_field.items():
        if isinstance(column.type, supported_type):
            break
    else:
        return {}

    kwargs = {"attribute": attribute or column.name, "default": default, "required": required}
    if issubclass(field_type, JSONWithModelField):
        json_type: JSONWithModel = column.type

        if flatten_jsons and not json_type.as_list:
            root_name: str = name
            return {k: move_field_attribute(root_name, k, v) for k, v in json_type.model.items()}

        field = json_type.model
        if isinstance(json_type.model, dict):
            field = NestedField(flask_restx_has_bad_design.model(json_type.model_name, field),
                                **({} if column.type.as_list else kwargs))
        if column.type.as_list:
            field = ListField(field, **kwargs)
        # field: RawField = field_type.create(column, column_type, default)
    else:
        if field_type == EnumField:
            enum = column.type.enum_class
            if isinstance(enum, type) and issubclass(enum, TypeEnum):
                kwargs["enum"] = enum.get_all_field_names()
            else:
                kwargs["enum"] = column.type.enums
        field = field_type(**kwargs)

    return {name: field}


@dataclass()
class LambdaFieldDef:
    """
    DEPRECATED (in favour OF :class:`Model` below)

    A field to be used in create_marshal_model, which can't be described as a :class:`Column`.

    - model_name — global name of the model to connect the field to.
    - field_type — field's return type (:class:`bool`, :class:`int`, :class:`str` or :class:`datetime`).
    - attribute — the attribute to pass to the field's keyword argument ``attribute``.
      can be a :class:`Callable` that uses models pre-marshalled version.
    """

    model_name: str
    field_type: type
    attribute: Union[str, Callable]
    name: Union[str, None] = None

    def to_field(self) -> Union[Type[RawField], RawField]:
        field_type: Type[RawField] = RawField
        for supported_type in type_to_field:
            if issubclass(self.field_type, supported_type):
                field_type = type_to_field[supported_type]
                break
        return field_type(attribute=self.attribute)


def create_marshal_model(model_name: str, *fields: str, inherit: Union[str, None] = None,
                         use_defaults: bool = False, flatten_jsons: bool = False):
    """
    DEPRECATED (in favour OF :class:`Model` below)

    - Adds a marshal model to a database object, marked as :class:`Marshalable`.
    - Automatically adds all :class:`LambdaFieldDef`-marked class fields to the model.
    - Sorts modules keys by alphabet and puts ``id`` field on top if present.
    - Uses kebab-case for json-names.

    :param model_name: the **global** name for the new model or model to be overwritten.
    :param fields: filed names of columns to be added to the model.
    :param inherit: model name to inherit fields from.
    :param use_defaults: whether to describe columns' defaults in the model.
    :param flatten_jsons: whether to put inner JSON fields in the root model or as a Nested field
    """

    def create_marshal_model_wrapper(cls):
        model_dict = {} if inherit is None else cls.marshal_models[inherit].copy()

        model_dict.update({
            k: v
            for column in cls.__table__.columns
            if column.name in fields
            for k, v in create_fields(column, column.name.replace("_", "-"), use_defaults, flatten_jsons).items()
        })

        model_dict.update({
            field_name.replace("_", "-") if field.name is None else field.name: field.to_field()
            for field_name, field_type in get_type_hints(cls).items()
            if isinstance(field_type, type) and issubclass(field_type, LambdaFieldDef)
            if (field := getattr(cls, field_name)).model_name == model_name
        })

        cls.marshal_models[model_name] = OrderedDict(sorted(model_dict.items()))
        if "id" in cls.marshal_models[model_name].keys():
            cls.marshal_models[model_name].move_to_end("id", last=False)

        return cls

    return create_marshal_model_wrapper


class Marshalable:
    """ DEPRECATED (in favour OF :class:`Model` below)
    Marker-class for classes that can be decorated with ``create_marshal_model``
    """
    marshal_models: dict[str, OrderedDict[str, Type[RawField]]] = {}


def unite_models(*models: dict[str, Union[Type[RawField], RawField]]):
    """
    - Unites several field dicts (models) into one.
    - If some fields are present in more than one model, the last encounter will be used.
    - Sorts modules keys by alphabet and puts ``id`` field on top if present.

    :param models: models (dicts of field definitions) to unite
    :return: united model with all fields
    """

    model_dict: OrderedDict = OrderedDict()
    for model in models:
        model_dict.update(model)
    model_dict = OrderedDict(sorted(model_dict.items()))
    if "id" in model_dict.keys():
        model_dict.move_to_end("id", last=False)
    return model_dict


@dataclass()
class ResponseDoc:
    """ Dataclass to keep the response description is one place """

    code: Union[int, str] = 200
    description: str = None
    model: Union[_Model, None] = None

    @classmethod
    def error_response(cls, code: Union[int, str], description: str) -> ResponseDoc:
        """ Creates an instance of an :class:`ResponseDoc` with a message response model for the response body """
        return cls(code, description)

    def register_model(self, ns: Namespace):
        if self.model is not None:
            self.model = ns.model(self.model.name, self.model)

    def get_args(self) -> Union[tuple[Union[int, str], str], tuple[Union[int, str], str, _Model]]:
        if self.model is None:
            return self.code, self.description
        return self.code, self.description, self.model


t = TypeVar("t", bound="Model")
Undefined = object()


class Model(Nameable):
    """ A base class for models
    Can be combined with dataclasses, Pydantic or Marshmallow to define fields
    Instances will be passed as data for flask_restx's marshal function
    """

    @staticmethod
    def include_columns(*columns: Column, _use_defaults: bool = False, _flatten_jsons: bool = False,
                        _require_all: bool = None, **named_columns: Column) -> Callable[[Type[t]], Type[t]]:
        named_columns = {key.replace("_", "-"): value for key, value in named_columns.items()}

        # TODO allow different cases

        # TODO Maybe allow *columns: Column to do this here:
        #   (doesn't work for models inside DB classes, as Column.name is populated later)
        #   named_columns.update({column.name.replace("_", "-"): column for column in columns})

        def include_columns_inner(cls: Type[t]) -> Type[t]:
            fields = {}

            class ModModel(cls):
                __columns_converted__ = False

                @classmethod
                def convert_columns(cls):  # TODO find a better way, Nameable, perhaps?
                    if not cls.__columns_converted__:
                        if hasattr(super(), "convert_columns"):
                            super().convert_columns()  # noqa
                        named_columns.update({column.name.replace("_", "-"): column for column in columns})
                        for name, column in named_columns.items():
                            fields.update(
                                create_fields(column, name, _use_defaults, _flatten_jsons, _require_all, name))
                        cls.__columns_converted__ = True

                # TODO make model's ORM attributes usable (__init__?)
                #   XOR use class properties for Columns in a different way
                @classmethod
                def convert(cls: Type[t], orm_object, **context) -> t:
                    cls.convert_columns()
                    result: cls = super().convert(orm_object, **context)
                    for name, column in named_columns.items():
                        object.__setattr__(result, name, getattr(orm_object, column.name or name.replace("-", "_")))
                    return result

                @classmethod
                def model(cls) -> dict[str, RawField]:
                    cls.convert_columns()
                    return dict(super().model(), **fields)

                @classmethod
                def deconvert(cls: Type[t], data: dict[str, ...]) -> t:
                    cls.convert_columns()
                    result: cls = super().deconvert(data)
                    for name, column in named_columns.items():
                        value = data.get(name, Undefined)
                        if value is not Undefined:
                            object.__setattr__(result, column.name, value)
                    return result

                @classmethod
                def parser(cls, **kwargs) -> RequestParser:
                    cls.convert_columns()
                    result: RequestParser = super().parser(**kwargs)
                    for name, column in named_columns.items():
                        data: dict[str, ...] | None = sqlalchemy_column_to_kwargs(column)
                        if data is not None:
                            result.add_argument(name, dest=column.name, **data, **kwargs)
                    return result

            return ModModel

        return include_columns_inner

    @classmethod
    def named_column_model(cls: Type[t], _name: str, *columns: Column, **kwargs) -> Type[t]:
        @cls.include_columns(*columns, **kwargs)
        class ModModel(cls):
            name = _name

        return ModModel

    @classmethod
    def column_model(cls: Type[t], *columns: Column, **kwargs) -> Type[t]:
        # only use as a property in a subclass of NamedProperties!
        @cls.include_columns(*columns, **kwargs)
        class ModModel(cls):
            pass

        return ModModel

    @staticmethod
    def include_nest_model(model: Type[Model], field_name: str, parameter_name: str = None,
                           as_list: bool = False, required: bool = True) -> Callable[[Type[t]], Type[t]]:
        if parameter_name is None:
            parameter_name = field_name

        def include_nest_model_inner(cls: Type[t]) -> Type[t]:
            class ModModel(cls):
                @classmethod
                def convert(cls: Type[t], orm_object, **context) -> t:
                    nested = getattr(orm_object, parameter_name)
                    if as_list:
                        nested = [model.convert(item, **context) for item in nested]
                    else:
                        nested = model.convert(nested, **context)

                    result: cls = super().convert(orm_object, **context)
                    object.__setattr__(result, field_name, nested)
                    return result

                @classmethod
                def model(cls) -> dict[str, RawField]:  # TODO workaround, replace with recursive registration
                    return dict(super().model(), **{field_name: NestedField(
                        flask_restx_has_bad_design.model(name=model.name, model=model.model()),
                        required=required, as_list=as_list)})

                @classmethod
                def deconvert(cls: Type[t], data: dict[str, ...]) -> t:
                    result: cls = super().deconvert(data)
                    object.__setattr__(result, parameter_name, data[field_name])
                    return result

                @classmethod
                def parser(cls, **kwargs) -> RequestParser:
                    raise ValueError("Nested structures are not supported")

            return ModModel

        return include_nest_model_inner

    @classmethod
    def nest_model(cls, model: Type[Model], field_name: str, parameter_name: str = None,
                   as_list: bool = False) -> Type[t]:
        @cls.include_nest_model(model, field_name, parameter_name, as_list)
        class ModModel(cls):
            pass

        return ModModel

    # TODO include_relationship decorator & relationship_model metagenerator-classmethod

    @staticmethod
    def include_model(model: Type[Model]) -> Callable[[Type[t]], Type[t]]:
        def include_model_inner(cls: Type[t]) -> Type[t]:
            class ModModel(cls, model):
                pass

            return ModModel

        return include_model_inner

    @classmethod
    def combine_with(cls, model: Type[Model]) -> Type[t]:
        # only use as a property in a subclass of NamedProperties!
        class ModModel(cls, model):
            pass

        return ModModel

    @staticmethod
    def include_context(*names, **var_types) -> Callable[[Type[t]], Type[t]]:  # TODO Maybe redo
        var_types.update({name: object for name in names})

        def include_context_inner(cls: Type[t]) -> Type[t]:
            class ModModel(cls):
                @classmethod
                def convert(cls: Type[t], orm_object, **context) -> t:
                    assert all((value := context.get(name, None)) is not None
                               and isinstance(value, var_type)
                               for name, var_type in var_types.items()), \
                        "Context was not filled properly"  # TODO better error messages!
                    return super().convert(orm_object, **context)

            return ModModel

        return include_context_inner

    @classmethod
    def convert(cls: Type[t], orm_object, **context) -> t:
        raise NotImplementedError()

    @classmethod
    def model(cls) -> dict[str, Union[Type[RawField], RawField]]:
        raise NotImplementedError()

    @classmethod
    def deconvert(cls: Type[t], data: dict[str, ...]) -> t:
        # TODO version of deconvert for parsing (see argument parser as well)
        raise NotImplementedError()

    @classmethod
    def parser(cls, **kwargs) -> RequestParser:
        raise NotImplementedError()


class PydanticModel(BaseModel, Model, ABC):
    @staticmethod
    def pydantic_to_restx_field(field: ModelField) -> RawField:
        if isinstance(field.type_, ForwardRef):
            raise NotImplementedError()

        if issubclass(field.type_, Model):
            result = NestedField(flask_restx_has_bad_design.model(field.type_.name, field.type_.model()),
                                 **pydantic_field_to_kwargs(field))
        elif issubclass(field.type_, TypeEnum):
            result = StringField(enum=field.type_.get_all_field_names(), **pydantic_field_to_kwargs(field))
        else:
            result = type_to_field[field.type_](**pydantic_field_to_kwargs(field))

        if field.type_ is not field.outer_type_:
            result = ListField(result, **pydantic_field_to_kwargs(field))
        result.attribute = field.name
        return result

    @classmethod
    def model(cls) -> dict[str, RawField]:
        return {field.alias.replace("_", "-"): PydanticModel.pydantic_to_restx_field(field)
                for name, field in cls.__fields__.items()}

    @classmethod
    def parser(cls, **kwargs) -> RequestParser:
        parser: RequestParser = RequestParser()
        field: ModelField
        for name, field in cls.__fields__.items():
            if field.type_ is not field.outer_type_:
                kwargs["action"] = "append"
            elif field.is_complex():
                raise ValueError("Nested structures are not supported")  # TODO flat-nested fields support
            parser.add_argument(field.alias.replace("_", "-"), dest=name, type=field.type_,
                                **pydantic_field_to_kwargs(field), **kwargs)
        return parser

    @classmethod
    def callback_convert(cls, callback: Callable, orm_object, **context) -> None:
        pass

    @classmethod
    def dict_convert(cls, orm_object, **context) -> dict[str, ...]:
        result = {}
        cls.callback_convert(result.update, orm_object, **context)
        return result

    @classmethod
    def convert(cls: Type[t], orm_object, **context) -> t:
        return cls(**cls.dict_convert(orm_object, **context))

    @classmethod
    def parse_obj(cls: Type[t], obj: ...) -> t:
        return cls.deconvert(obj)

    @classmethod
    def deconvert(cls: Type[t], data: dict[str, ...]) -> t:
        return super().parse_obj(data)
