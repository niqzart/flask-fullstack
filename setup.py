from setuptools import setup, find_packages

description = (
    "A utility package for projects using flask, sqlalchemy, socketio and pytest"
)
with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="flask-fullstack",
    py_modules=["flask_fullstack"],
    version="0.4.12",
    description=description,
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="niqzart",
    author_email="qwert45hi@yandex.ru",
    url="https://github.com/niqzart/flask-fullstack",
    packages=find_packages(),
    install_requires=[
        "Flask-Cors ~= 3.0.10",
        "Flask-JWT-Extended ~= 4.3.1",
        "Flask-RESTX ~= 1.0.3",
        "Flask-SQLAlchemy ~= 3.0.2",
        "Flask-SocketIO ~= 5.1.0",
        "pydantic ~= 1.9.0",
        "SQLAlchemy ~= 1.4.31",
        "Whoosh ~= 2.7.4",
        "WhooshAlchemy ~= 0.3.1",
    ],
    extras_require={
        "dev": [
            "pytest",
        ],
    },
)
