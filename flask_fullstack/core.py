from collections.abc import Callable
from datetime import timedelta, datetime, timezone
from logging.config import dictConfig
from os import getenv
from traceback import format_tb
from typing import Type

from flask import Flask as _Flask, Response, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager, get_jwt, set_access_cookies, create_access_token, get_jwt_identity, \
    unset_jwt_cookies
from flask_restx import Api
from sqlalchemy import create_engine, MetaData
from werkzeug.exceptions import NotFound

from .marshals import flask_restx_has_bad_design
from .sqlalchemy import Sessionmaker, create_base, ModBase, Session
from .whoosh import IndexService


class Flask(_Flask):
    def __init__(self, *args, versions=None, **kwargs):
        super().__init__(*args, **kwargs)
        if versions is None:
            self.versions = {}
        else:
            self.versions = versions

    def debug_from_env(self, default=True) -> None:
        self.debug = default != (getenv("DEBUG", None) is not None)

    def secrets_from_env(self, default) -> None:
        for secret_name in ["SECRET_KEY", "SECURITY_PASSWORD_SALT", "JWT_SECRET_KEY", "API_KEY"]:
            self.config[secret_name] = getenv(secret_name, default)

    def configure_cors(self) -> None:
        CORS(self, supports_credentials=True)

    def configure_restx(self, use_jwt: bool = True) -> Api:
        self.config["PROPAGATE_EXCEPTIONS"] = True
        authorizations = {
            "jwt": {
                "type": "apiKey",
                "in": "cookie",
                "name": "access_token_cookie"
            }
        } if use_jwt else None
        api = Api(self, doc="/doc/", version=self.versions.get("API", None), authorizations=authorizations)
        api.add_namespace(flask_restx_has_bad_design)  # TODO workaround
        return api

    def return_error(self, code: int, message: str):
        return Response(message, status=code)

    def configure_error_handlers(self, log_stuff: Callable[[str, str], None]):  # TODO redo with `logging`
        @self.errorhandler(NotFound)
        def on_not_found(_):
            return self.return_error(404, "Not Found")

        @self.errorhandler(Exception)
        def on_any_exception(error: Exception):
            error_text: str = f"Requested URL: {request.path}\nError: {repr(error)}\n" + \
                              "".join(format_tb(error.__traceback__))
            log_stuff("error", error_text)
            return self.return_error(500, error_text)

    def configure_jwt_manager(self, location: list[str], access_expires: timedelta, samesite_cookie: str = "None",
                              csrf_protect: bool = True) -> JWTManager:
        self.config["JWT_TOKEN_LOCATION"] = location
        self.config["JWT_COOKIE_CSRF_PROTECT"] = csrf_protect
        self.config["JWT_COOKIE_SAMESITE"] = samesite_cookie
        self.config["JWT_COOKIE_SECURE"] = samesite_cookie == "None"
        self.config["JWT_BLACKLIST_ENABLED"] = True
        self.config["JWT_ACCESS_TOKEN_EXPIRES"] = access_expires
        self.config["JWT_BLACKLIST_TOKEN_CHECKS"] = ["access"]

        jwt = JWTManager(self)

        @self.after_request
        def refresh_expiring_jwt(response: Response):
            try:
                target_timestamp = datetime.timestamp(datetime.now(timezone.utc) + timedelta(hours=36))
                if target_timestamp > get_jwt()["exp"]:
                    set_access_cookies(response, create_access_token(identity=get_jwt_identity()))
                return response
            except (RuntimeError, KeyError):
                return response

        return jwt

    def configure_jwt_with_loaders(self, location: list[str], access_expires: timedelta,
                                   log_stuff: Callable[[str, str], None], samesite_cookie: str = "None",
                                   csrf_protect: bool = True) -> JWTManager:
        jwt = self.configure_jwt_manager(location, access_expires, samesite_cookie, csrf_protect)

        @jwt.expired_token_loader
        def expired_token_callback(*_):
            response = self.return_error(401, "expired token")
            unset_jwt_cookies(response)
            return response

        @jwt.token_verification_failed_loader
        def verification_failed_callback(*_):
            log_stuff("error", f"Token verification somehow failed\n[`{datetime.utcnow()}`]")
            response = self.return_error(401, "token verification failed")
            unset_jwt_cookies(response)
            return response

        @jwt.invalid_token_loader
        def invalid_token_callback(callback):
            log_stuff("error", f"Invalid token: {callback}\n[`{datetime.utcnow()}`]")
            response = self.return_error(422, f"invalid token: {callback}")
            unset_jwt_cookies(response)
            return response

        @jwt.unauthorized_loader
        def unauthorized_callback(callback: str):
            if callback.startswith("Missing cookie"):
                log_stuff("error", f"Unauthorized: {callback}\n[`{datetime.utcnow()}`]")
            response = self.return_error(401, f"unauthorized: {callback}")
            unset_jwt_cookies(response)
            return response

        return jwt


def configure_logging(config: dict):
    dictConfig(config)


def configure_sqlalchemy(db_url: str, **engine_kwargs) -> tuple[MetaData, Type[ModBase], Sessionmaker]:
    engine = create_engine(db_url, pool_recycle=280, **engine_kwargs)
    return (db_meta := MetaData(bind=engine)), create_base(db_meta), Sessionmaker(bind=engine, class_=Session)


def configure_whooshee(sessionmaker: Sessionmaker, whoosh_base: str):
    whooshee_config = {
        "WHOOSHEE_MIN_STRING_LEN": 0,
        "WHOOSHEE_ENABLE_INDEXING": True,
        "WHOOSH_BASE": whoosh_base,
    }
    return IndexService(config=whooshee_config, session=sessionmaker())
