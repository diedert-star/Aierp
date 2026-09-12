import enum

from sqlalchemy import Enum


def pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """A Postgres-backed SQLAlchemy Enum column storing the member VALUE, not its name."""
    return Enum(enum_cls, name=name, values_callable=lambda obj: [e.value for e in obj])
