import json
import re
from typing import Any

from app.repository import repo


IMAGE_MD_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip()
    text = IMAGE_MD_RE.sub(r"[изображение: \1]", text)
    return text


def current_status_text(front_members: list[dict[str, Any]]) -> str:
    if not front_members:
        return "блюр"
    names = ", ".join(member["name"] for member in front_members)
    return f"фронт - {names}"


async def format_member_info(member: dict[str, Any]) -> str:
    raw = json.loads(member.get("raw_json") or "{}")
    categories = await repo.get_categories_for_member(member["id"])
    custom_fields = await repo.get_custom_fields_map()

    parts: list[str] = []
    name = _clean_text(member.get("name"))
    parts.append(name)

    pronouns = _clean_text(member.get("pronouns"))
    if pronouns:
        parts.append(f"Местоимения: {pronouns}")
    else:
        parts.append("Местоимения: не указаны")

    if categories:
        parts.append("Категории:\n" + "\n".join(f"- {cat}" for cat in categories))
    else:
        parts.append("Категории:\nне указаны")

    description = await repo.replace_member_mentions(_clean_text(member.get("description")))
    if description:
        parts.append("Описание:\n" + description)

    info = raw.get("info") or {}
    if isinstance(info, dict):
        custom_parts = []
        for field_id, value in info.items():
            value_text = await repo.replace_member_mentions(_clean_text(value))
            if not value_text:
                continue
            field_name = custom_fields.get(field_id, field_id)
            custom_parts.append(f"{field_name}:\n{value_text}")
        if custom_parts:
            parts.append("Дополнительная информация:\n" + "\n\n".join(custom_parts))

    if member.get("is_archived"):
        reason = _clean_text(member.get("archived_reason"))
        parts.append("Архив: да" + (f" ({reason})" if reason else ""))

    return "\n\n".join(parts)


async def format_front_info(front_members: list[dict[str, Any]]) -> str:
    if not front_members:
        return "Сейчас: блюр\n\nНа фронте никого нет."

    chunks = ["Сейчас на фронте:"]
    for member in front_members:
        chunks.append(await format_member_info(member))
    return "\n\n—————\n\n".join(chunks)


def split_long_message(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for block in text.split("\n\n"):
        block_len = len(block) + 2
        if current and current_len + block_len > limit:
            chunks.append("\n\n".join(current))
            current = [block]
            current_len = block_len
        else:
            current.append(block)
            current_len += block_len

    if current:
        chunks.append("\n\n".join(current))

    final_chunks: list[str] = []
    for chunk in chunks:
        if len(chunk) <= limit:
            final_chunks.append(chunk)
        else:
            for i in range(0, len(chunk), limit):
                final_chunks.append(chunk[i:i + limit])
    return final_chunks
