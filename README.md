# Flask-Fullstack
Flask-Fullstack is an utils package for projects using a fleet of libs: 
- [Flask](https://flask.palletsprojects.com/en/2.2.x/)
- [Flask-RESTX](https://flask-restx.readthedocs.io/en/latest/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [SocketIO](https://socket.io/) & [Flask-SocketIO](https://flask-socketio.readthedocs.io/en/latest/)
- [pytest](https://docs.pytest.org/en/7.1.x/)

It is currently in deep development, I'd call the current version 0.0.13. 
Package is maintained by one programmer ([hey that me!](https://github.com/niqzart)). 
In this readme you can find:
- [Install instructions](#install)
- [Quick start guide](#quick-start)
- [Current features](#features)
- [Planned features](#future)

## Install
TBD

## Quick Start
TBD

## Features
### Interfaces & Mixins
- [Database Interfaces](./docs/database-interfaces.md): Implement these to later automate searching & authorization (see below)
- Mixins with Decorators: Classes full of useful decorators to be used in less abstract context (see below)

### RESTX improvements
- New Marshals: form SQLAlchemy to Pydantic and then to the Response Marshaling
- [Upgraded Parsers](./docs/upgraded-parsers.md): just a couple of commonly used parsers to `.copy()`
- Resource Controller: RESTX's Namespace, but with access to useful decorators from mixins

#### New Models
New models, created in `flask_fullstack.restx.marshals`, are a translation layer between Pydantic & RESTX's own Models. These models also support being created from SQLAlchemy tables via Column reflection

For Pydantic, it only supports as fields: the keys of `flask_fullstack.restx.marshals.type_to_field`, `list`s and nesting other Pydantic models

For SQLAlchemy, it only supports converting columns of types in the keys of `flask_fullstack.restx.marshals.column_to_field`

## SocketIO eXtensions
- Understandable Events: Makes possible automatic documentation, data validation (with New Marshals or pure Pydantic) & emits not just by the event's name
- Event Controller: Used to group events & provide access to useful decorators from mixins
- Upgraded Structures: Propagating new events & other utils to Flask-SocketIO's `Namespace`s & the `SocketIO` class itself

## Other Utils
- SQLAlchemy Simplified: creating objects, parsing query results, deleting objects
- New Columns: JSON with Schema or a RESTX Model to use in New Marshals
- Named: If some class attribute needs to know the attribute name
- Other: Utils for dicts, pydantic, pytest, unpacking RESTX responses, TypeEnum, etc
- Core: For simplifying the common project setup steps

## Future
TBA

## Contributing
You are welcome to create issues and PRs in this repository. I'll get to them as soon as I have time!
