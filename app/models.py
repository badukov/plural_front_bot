from dataclasses import dataclass


@dataclass(frozen=True)
class Member:
    id: str
    name: str
    pronouns: str | None
    description: str | None
    color: str | None
    is_private: bool
    is_archived: bool
    archived_reason: str | None
    raw_json: dict


@dataclass(frozen=True)
class Group:
    id: str
    parent_id: str | None
    name: str
    emoji: str | None
    description: str | None
    is_private: bool
    raw_json: dict
