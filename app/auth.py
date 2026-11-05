"""Small token-to-principal authorization layer for the deployment MVP."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    name: str
    role: str
    shops: tuple[str, ...] = ()

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class AuthorizationError(PermissionError):
    """Raised when an authenticated principal is outside its data scope."""


def authenticate(token: str | None) -> Principal | None:
    """Map configured API tokens to roles; never trust a client-supplied role."""
    admin_token = os.getenv("API_AUTH_TOKEN")
    if admin_token and token and secrets.compare_digest(token, admin_token):
        return Principal(name="admin", role="admin")

    operator_token = os.getenv("OPERATOR_API_TOKEN")
    if operator_token and token and secrets.compare_digest(token, operator_token):
        shops = tuple(
            item.strip()
            for item in os.getenv("OPERATOR_SHOPS", "").split(",")
            if item.strip()
        )
        return Principal(name="operator", role="operator", shops=shops)
    return None
