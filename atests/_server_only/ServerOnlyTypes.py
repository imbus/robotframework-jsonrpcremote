"""A type that only the server has: the client cannot import this folder."""

from dataclasses import dataclass


@dataclass
class OnlyOnTheServer:
    value: int
