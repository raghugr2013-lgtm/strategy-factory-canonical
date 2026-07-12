"""Domain models — Pydantic v2 with PyObjectId support."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from typing_extensions import Annotated


def _coerce_object_id(v: Any) -> str:
    if v is None:
        return v
    if isinstance(v, ObjectId):
        return str(v)
    return str(v)


PyObjectId = Annotated[str, BeforeValidator(_coerce_object_id)]

Role = Literal["admin", "developer", "researcher", "operator", "viewer"]
ALL_ROLES: tuple[str, ...] = ("admin", "developer", "researcher", "operator", "viewer")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: dict | None):
        if doc is None:
            return None
        return cls.model_validate(doc)

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude_none=True)
        if data.get("_id") is None:
            data.pop("_id", None)
        return data


class User(BaseDocument):
    user_id: str
    email: str
    password_hash: str
    name: Optional[str] = None
    role: Role = "viewer"
    status: Literal["active", "disabled", "pending"] = "active"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class UserPublic(BaseModel):
    user_id: str
    email: str
    name: Optional[str] = None
    role: Role
    status: str
    created_at: datetime


class RefreshToken(BaseDocument):
    jti: str
    user_id: str
    expires_at: datetime
    revoked: bool = False
    created_at: datetime = Field(default_factory=utcnow)
