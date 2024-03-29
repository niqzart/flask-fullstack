from __future__ import annotations

import warnings
from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from types import UnionType
from typing import Any, ClassVar, ForwardRef, TypeVar, get_args, get_origin

import pydantic as pydantic_v2
import pydantic.v1 as pydantic_v1  # noqa: WPS301
from flask_restx import Model as _Model, Namespace
from flask_restx.fields import (
    Boolean as BooleanField,
    Float as FloatField,
    Integer as IntegerField,
    List as ListField,
    Nested as NestedField,
    Raw as RawField,
    String as StringField,
)
from flask_restx.reqparse import RequestParser
from pydantic.v1 import BaseModel
from pydantic.v1.fields import ModelField
from pydantic_core import PydanticUndefined
from pydantic_marshals.utils import is_subtype
from sqlalchemy import Column, Date, Float, Sequence, Time
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.types import JSON, Boolean, DateTime, Enum, Integer, String
from typing_extensions import Self

from ..utils import JSONWithModel, Nameable, TypeEnum


class EnumField(StringField):
    def format(self, value: TypeEnum) -> str:
        return value.to_string()


class DateTimeField(StringField):
    def format(self, value: datetime) -> str:
        return value.isoformat()


class DateField(StringField):
    def format(self, value: date) -> str:
        return value.isoformat()


class TimeField(StringField):
    def format(self, value: time) -> str:
        return value.isoformat()


class JSONLoadableField(RawField):
    def format(self, value):
        return value


# class ConfigurableField:
#     @classmethod
#     def create(cls, column: Column, column_type: Union[type[typeEngine], typeEngine],
#                default=None) -> Union[RawField, type[RawField]]:
#         raise NotImplementedError


class JSONWithModelField:
    pass


type_to_field: dict[type, type[RawField]] = {
    bool: BooleanField,
    int: IntegerField,
    float: FloatField,
    str: StringField,
    dict: JSONLoadableField,
    JSON: JSONLoadableField,
    time: TimeField,
    date: DateField,
    datetime: DateTimeField,
}

column_to_field: dict[type[TypeEngine], type[RawField]] = {
    JSONWithModel: JSONWithModelField,
    JSON: JSONLoadableField,
    DateTime: DateTimeField,
    Date: DateField,
    Time: TimeField,
    Enum: EnumField,
    Boolean: BooleanField,
    Integer: IntegerField,
    Float: FloatField,
    String: StringField,
}

column_to_type: dict[type[TypeEngine], type] = {
    DateTime: datetime,
    Boolean: bool,
    Integer: int,
    Float: float,
    String: str,
}


def pydantic_field_to_kwargs(field: ModelField) -> dict[str, ...]:
    return {
        "default": field.default,
        "required": field.required,
        "allow_null": not field.required,
    }


def sqlalchemy_column_to_kwargs(column: Column) -> dict[str, ...] | None:
    result: dict[str, ...] = {
        "default": column.default,
        "required": not column.nullable and column.default is None,
    }

    for supported_type, type_ in column_to_field.items():
        if isinstance(column.type, supported_type):
            result["type"] = type_
            return result

    if isinstance(column.type, Enum):
        result["type"] = str
        # result["choices"] = column.type  # TODO support for enums with a renewed TypeEnum field
        return result


flask_restx_has_bad_design: Namespace = Namespace("this-is-dumb")


def move_field_attribute(
    root_name: str,
    field_name: str,
    field_def: type[RawField] | RawField,
):
    attribute_name: str = f"{root_name}.{field_name}"
    if isinstance(field_def, type):
        return field_def(attribute=attribute_name)
    field_def.attribute = attribute_name
    return field_def


def create_fields(
    column: Column,
    name: str,
    use_defaults: bool = False,
    flatten_jsons: bool = False,
    required: bool = None,
    attribute: str = None,
) -> dict[str, ...]:
    if (
        not use_defaults
        or column.default is None
        or column.nullable
        or isinstance(column.default, Sequence)
    ):
        default = None
        required = required or not column.nullable
    else:
        default = column.default.arg
        required = required or False

    for supported_type, field_type in column_to_field.items():  # noqa: B007
        if isinstance(column.type, supported_type):
            break
    else:
        raise TypeError(f"{column.type} is not supported")

    kwargs = {
        "attribute": attribute or column.name,
        "default": default,
        "required": required,
    }
    if issubclass(field_type, JSONWithModelField):
        json_type: JSONWithModel = column.type

        if flatten_jsons and not json_type.as_list:
            root_name: str = name
            return {
                k: move_field_attribute(root_name, k, v)
                for k, v in json_type.model.items()
            }

        field = json_type.model
        if isinstance(json_type.model, dict):
            field = NestedField(
                flask_restx_has_bad_design.model(json_type.model_name, field),
                **({} if column.type.as_list else kwargs),
            )
        if column.type.as_list:
            field = ListField(field, **kwargs)
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
class ResponseDoc:
    """Dataclass to keep the response description is one place"""

    code: int | str = 200
    description: str = None
    model: _Model | None = None

    @classmethod
    def error_response(cls, code: int | str, description: str) -> ResponseDoc:
        """
        Creates an instance of an :class:`ResponseDoc` with
        a message response model for the response body
        """
        return cls(code, description)

    def register_model(self, ns: Namespace):
        if self.model is not None:
            self.model = ns.model(self.model.name, self.model)

    def get_args(self) -> tuple[int | str, str] | tuple[int | str, str, _Model]:
        if self.model is None:
            return self.code, self.description
        return self.code, self.description, self.model


t = TypeVar("t", bound="Model")
Undefined = object()


class Model(Nameable):
    """A base class for models
    Can be combined with dataclasses, Pydantic or Marshmallow to define fields
    Instances will be passed as data for flask_restx's marshal function
    """

    @staticmethod
    def include_columns(
        *columns: Column,
        _use_defaults: bool = False,
        _flatten_jsons: bool = False,
        _require_all: bool = None,
        **named_columns: Column,
    ) -> Callable[[type[t]], type[t]]:
        named_columns = {
            key.replace("_", "-"): value for key, value in named_columns.items()
        }

        # TODO allow different cases

        # TODO Maybe allow *columns: Column to do this here:
        #   (doesn't work for models inside DB classes, as Column.name is populated later)
        #   named_columns.update

        def include_columns_inner(cls: type[t]) -> type[t]:
            fields = {}

            class ModModel(cls):
                __columns_converted__ = False

                @classmethod
                def convert_columns(cls):  # TODO find a better way, Nameable, perhaps?
                    if not cls.__columns_converted__:
                        if hasattr(super(), "convert_columns"):
                            super().convert_columns()  # noqa
                        named_columns.update(
                            {
                                column.name.replace("_", "-"): column
                                for column in columns
                            }
                        )
                        for name, column in named_columns.items():
                            fields.update(
                                create_fields(
                                    column,
                                    name,
                                    _use_defaults,
                                    _flatten_jsons,
                                    _require_all,
                                    name,
                                )
                            )
                        cls.__columns_converted__ = True

                # TODO make model's ORM attributes usable (__init__?)
                #   XOR use class properties for Columns in a different way
                @classmethod
                def convert_one(cls, orm_object, **context) -> Self:
                    cls.convert_columns()
                    result: cls = super().convert_one(orm_object, **context)
                    for name, column in named_columns.items():
                        object.__setattr__(
                            result,
                            name,
                            getattr(orm_object, column.name or name.replace("-", "_")),
                        )
                    return result

                @classmethod
                def model(cls) -> dict[str, RawField]:
                    cls.convert_columns()
                    return dict(super().model(), **fields)

                @classmethod
                def deconvert_one(cls, data: dict[str, ...]) -> Self:
                    cls.convert_columns()
                    result: cls = super().deconvert_one(data)
                    for (
                        name,
                        column,
                    ) in named_columns.items():  # TODO raise parsing errors
                        value = data.get(name, column.default)
                        if (
                            isinstance(column.type, Enum)
                            and isinstance(column.type.enum_class, type)
                            and issubclass(column.type.enum_class, TypeEnum)
                        ):
                            value = column.type.enum_class.from_string(value)
                        object.__setattr__(
                            result,
                            column.name,
                            value,
                        )
                    return result

                @classmethod
                def parser(cls, **kwargs) -> RequestParser:
                    cls.convert_columns()
                    result: RequestParser = super().parser(**kwargs)
                    for name, column in named_columns.items():
                        data: dict[str, ...] | None = sqlalchemy_column_to_kwargs(
                            column
                        )
                        if data is not None:
                            result.add_argument(
                                name,
                                dest=column.name,
                                **data,
                                **kwargs,
                            )
                    return result

            return ModModel

        return include_columns_inner

    @classmethod
    def named_column_model(
        cls: type[t],
        _name: str,
        *columns: Column,
        **kwargs,
    ) -> type[t]:
        @cls.include_columns(*columns, **kwargs)
        class ModModel(cls):
            name = _name

        return ModModel

    @classmethod
    def column_model(cls: type[t], *columns: Column, **kwargs) -> type[t]:
        # only use as a property in a subclass of NamedProperties!
        @cls.include_columns(*columns, **kwargs)
        class ModModel(cls):
            pass

        return ModModel

    @staticmethod
    def include_nest_model(
        model: type[Model] | type[pydantic_v2.BaseModel],
        field_name: str,
        parameter_name: str = None,
        as_list: bool = False,
        required: bool = True,
        skip_none: bool = True,
    ) -> Callable[[type[t]], type[t]]:
        if isinstance(model, type) and issubclass(model, pydantic_v2.BaseModel):
            model = v2_model_to_ffs(model)

        if parameter_name is None:
            parameter_name = field_name

        def include_nest_model_inner(cls: type[t]) -> type[t]:
            class ModModel(cls):
                @classmethod
                def convert_one(cls, orm_object, **context) -> Self:
                    nested = getattr(orm_object, parameter_name)
                    if as_list:
                        nested = [model.convert_one(item, **context) for item in nested]
                    elif nested is not None:
                        nested = model.convert_one(nested, **context)

                    result: cls = super().convert_one(orm_object, **context)
                    object.__setattr__(result, field_name, nested)
                    return result

                @classmethod
                def model(cls) -> dict[str, RawField]:
                    # TODO workaround, replace with recursive registration
                    return dict(
                        super().model(),
                        **{
                            field_name: NestedField(
                                flask_restx_has_bad_design.model(
                                    name=model.name, model=model.model()
                                ),
                                required=required,
                                as_list=as_list,
                                allow_null=not required,
                                skip_none=skip_none,
                            )
                        },
                    )

                @classmethod
                def deconvert_one(cls, data: dict[str, ...]) -> Self:
                    result: cls = super().deconvert_one(data)
                    object.__setattr__(result, parameter_name, data[field_name])
                    return result

                @classmethod
                def parser(cls, **_) -> RequestParser:
                    raise ValueError("Nested structures are not supported")

            return ModModel

        return include_nest_model_inner

    @classmethod
    def nest_model(
        cls,
        model: type[Model] | type[pydantic_v2.BaseModel],
        field_name: str,
        parameter_name: str = None,
        as_list: bool = False,
        required: bool = True,
        skip_none: bool = True,
    ) -> type[t]:
        @cls.include_nest_model(
            model,
            field_name,
            parameter_name,
            as_list,
            required,
            skip_none,
        )
        class ModModel(cls):
            pass

        return ModModel

    @staticmethod
    def include_flat_nest_model(
        model: type[Model] | type[pydantic_v2.BaseModel],
        parameter_name: str,
    ) -> Callable[[type[t]], type[t]]:
        if isinstance(model, type) and issubclass(model, pydantic_v2.BaseModel):
            model = v2_model_to_ffs(model)

        def include_flat_nest_model_inner(cls: type[t]) -> type[t]:
            class ModModel(cls):
                @classmethod
                def convert_one(cls, orm_object, **context) -> Self:
                    result: cls = super().convert_one(orm_object, **context)
                    nested = getattr(orm_object, parameter_name)
                    if nested is not None:
                        nested = model.convert_one(nested, **context)
                        for field_name in model.model():
                            object.__setattr__(
                                result,
                                field_name,
                                getattr(nested, field_name, None),
                            )
                    return result

                @classmethod
                def model(cls) -> dict[str, RawField]:
                    return dict(super().model(), **model.model())

                @classmethod
                def deconvert_one(cls, data: dict[str, ...]) -> Self:
                    raise NotImplementedError(
                        "Inner flattened model deconverting is not supported yet"
                    )

                @classmethod
                def parser(cls, **_) -> RequestParser:
                    raise ValueError("Nested structures are not supported")

            return ModModel

        return include_flat_nest_model_inner

    @classmethod
    def nest_flat_model(
        cls, model: type[Model] | type[pydantic_v2.BaseModel], parameter_name: str
    ) -> type[t]:
        @cls.include_flat_nest_model(model, parameter_name)
        class ModModel(cls):
            pass

        return ModModel

    # TODO include_relationship decorator & relationship_model metagenerator-classmethod

    @staticmethod
    def include_model(
        model: type[Model] | type[pydantic_v2.BaseModel],
    ) -> Callable[[type[t]], type[t]]:
        if isinstance(model, type) and issubclass(model, pydantic_v2.BaseModel):
            model = v2_model_to_ffs(model)

        def include_model_inner(cls: type[t]) -> type[t]:
            class ModModel(cls, model):
                pass

            return ModModel

        return include_model_inner

    @classmethod
    def combine_with(cls, model: type[Model] | type[pydantic_v2.BaseModel]) -> type[t]:
        if isinstance(model, type) and issubclass(model, pydantic_v2.BaseModel):
            model = v2_model_to_ffs(model)

        # only use as a property in a subclass of NamedProperties!
        class ModModel(cls, model):
            pass

        return ModModel

    @staticmethod  # TODO Maybe redo
    def include_context(*names, **var_types) -> Callable[[type[t]], type[t]]:
        var_types.update({name: object for name in names})

        def include_context_inner(cls: type[t]) -> type[t]:
            class ModModel(cls):
                @classmethod
                def convert_one(cls, orm_object, **context) -> Self:
                    assert all(
                        (value := context.get(name, None)) is not None
                        and isinstance(value, var_type)
                        for name, var_type in var_types.items()
                    ), "Context was not filled properly"  # TODO better error messages!
                    return super().convert_one(orm_object, **context)

            return ModModel

        return include_context_inner

    @classmethod
    def convert_one(cls, orm_object, **context) -> Self:
        raise NotImplementedError()

    @classmethod
    def convert(cls, orm_object, **context) -> Self:
        if isinstance(orm_object, cls):  # already converted
            return orm_object
        return cls.convert_one(orm_object, **context)

    @classmethod
    def model(cls) -> dict[str, type[RawField] | RawField]:
        raise NotImplementedError()

    @classmethod
    def deconvert_one(cls, data: dict[str, ...]) -> Self:
        # TODO version of deconvert for parsing (see argument parser as well)
        raise NotImplementedError()

    @classmethod
    def deconvert(cls, data: t | dict[str, ...]) -> Self:
        if isinstance(data, cls):  # already deconverted
            return data
        return cls.deconvert_one(data)

    @classmethod
    def parser(cls, **kwargs) -> RequestParser:
        raise NotImplementedError()


class PydanticModel(BaseModel, Model, ABC):
    @staticmethod
    def pydantic_to_restx_field(field: ModelField) -> RawField:
        if isinstance(field.type_, ForwardRef):
            raise NotImplementedError()

        kwargs = pydantic_field_to_kwargs(field)
        if issubclass(field.type_, Model):
            result = NestedField(
                flask_restx_has_bad_design.model(field.type_.name, field.type_.model()),
                **kwargs,
            )
        elif issubclass(field.type_, TypeEnum):
            result = StringField(
                attribute=lambda x: getattr(x, field.name).to_string(),
                enum=field.type_.get_all_field_names(),
                **kwargs,
            )
        else:
            result = type_to_field[field.type_](**kwargs)

        if field.type_ is not field.outer_type_:
            result = ListField(result, **pydantic_field_to_kwargs(field))
        result.attribute = result.attribute or field.name
        return result

    @classmethod
    def model(cls) -> dict[str, RawField]:
        return {
            field.alias.replace("_", "-"): PydanticModel.pydantic_to_restx_field(field)
            for name, field in cls.__fields__.items()
        }

    @classmethod
    def parser(cls, **kwargs) -> RequestParser:
        parser: RequestParser = RequestParser()
        field: ModelField
        for name, field in cls.__fields__.items():
            if field.type_ is not field.outer_type_:
                kwargs["action"] = "append"
            elif field.is_complex():  # TODO flat-nested fields support
                raise ValueError("Nested structures are not supported")
            parser.add_argument(
                field.alias.replace("_", "-"),
                dest=name,
                type=field.type_,
                **pydantic_field_to_kwargs(field),
                **kwargs,
            )
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
    def convert_one(cls, orm_object, **context) -> Self:
        return cls(**cls.dict_convert(orm_object, **context))

    @classmethod
    def model_validate(cls, obj: ...) -> Self:  # TODO seems like recursion...
        return cls.deconvert(obj)

    @classmethod
    def deconvert_one(cls, data: dict[str, ...]) -> Self:
        return super().parse_obj(data)


def de_optional(args: Any) -> Any:
    optional: bool = False
    result: Any = None
    for arg in args:
        if is_subtype(arg, type(None)):
            optional = True
        elif is_subtype(arg, pydantic_v2.BaseModel):
            result = arg
    if optional:
        return result
    return None


def v2_annotation_to_v1(annotation: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is UnionType and len(args) == 2:
        model = de_optional(args)
        if model is not None:
            return v2_model_to_ffs(model) | None
    if origin is list and is_subtype(args[0], pydantic_v2.BaseModel):
        return list[v2_model_to_ffs(args[0])]
    if is_subtype(annotation, pydantic_v2.BaseModel):
        return v2_model_to_ffs(annotation)
    return annotation


def v2_field_to_v1(
    field: pydantic_v2.fields.FieldInfo,
    optional: bool = False,
) -> pydantic_v1.fields.FieldInfo:
    kwargs = {"alias": field.alias}
    if field.default is not PydanticUndefined:
        kwargs["default"] = field.default
    elif optional:
        kwargs["default"] = None
    return pydantic_v1.Field(**kwargs)


class PydanticBase(PydanticModel):
    raw: ClassVar[type[pydantic_v2.BaseModel]]

    class Config:
        orm_mode = True

    @classmethod
    def convert_one(cls, orm_object, **context) -> Self:
        if context:
            warnings.warn("Context is deprecated", DeprecationWarning)
        return cls.from_orm(orm_object)


def v2_model_to_ffs(
    model: type[pydantic_v2.BaseModel],
    optional: bool = False,
) -> type[PydanticBase]:
    result = pydantic_v1.create_model(
        model.__name__,
        __base__=PydanticBase,
        **{
            f_name: (
                v2_annotation_to_v1(field.annotation),
                v2_field_to_v1(field, optional=optional),
            )
            for f_name, field in model.model_fields.items()
        },
    )
    result.name = model.__name__
    result.raw = model
    return result
