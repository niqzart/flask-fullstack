from setuptools import setup, find_packages

setup(
    name="Flask Fullstack",
    version="0.4.2",
    description="TBA",
    author="niqzart",
    author_email="qwert45hi@yandex.ru",
    url="https://github.com/niqzart/flask-fullstack",
    packages=find_packages(),
    install_requires=[
        "Flask-Cors ~= 3.0.10",
        "Flask-JWT-Extended ~= 4.3.1",
        "Flask-RESTX ~= 0.5.1",
        "Flask-SocketIO ~= 5.1.0",
        "pydantic ~= 1.9.0",
        "SQLAlchemy ~= 1.4.31",
        "Werkzeug == 2.0.2",  # for restx
        "Whoosh ~= 2.7.4",
        "WhooshAlchemy ~= 0.3.1",
    ],
    extras_require={
        "dev": [
            "pytest",
        ],
    },
)
