import json
import re
from typing import Any

from app.i18n import t
from app.repository import repo


IMAGE_MD_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip()
    text = IMAGE_MD_RE.sub(r"[изображение: \1]", text)
    return text


def current_status_text(front_members: list[dict[str, Any]], lang: str = "ru") -> str:
    if not front_members:
        return t("front_blur", lang)
    names = ", ".join(member["name"] for member in front_members)
    return t("front_status", lang, names=names)


async def format_member_brief(member: dict[str, Any], lang: str = "ru") -> str:
    parts: list[str] = []
    name = _clean_text(member.get("name")) or t("no_name", lang)
    parts.append(name)

    pronouns = _clean_text(member.get("pronouns")) or t("not_specified", lang)
    parts.append(f"{t('pronouns', lang)}: {pronouns}")

    years = await repo.get_category_values_for_member(member["id"], "Years of birth")
    parts.append(f"{t('birth_year', lang)}: {', '.join(years) if years else t('not_specified_f', lang)}")

    roles = await repo.get_category_values_for_member(member["id"], "Roles")
    parts.append(f"{t('role', lang)}: {', '.join(roles) if roles else t('not_specified_f', lang)}")

    if member.get("is_archived"):
        parts.append(t("archive_yes", lang))

    return "\n".join(parts)


async def format_members_brief_list(members: list[dict[str, Any]], lang: str = "ru") -> str:
    return "\n\n".join([await format_member_brief(member, lang) for member in members])


async def format_front_notification(event_text: str, front_members: list[dict[str, Any]], lang: str = "ru") -> str:
    status = current_status_text(front_members, lang)
    if not front_members:
        return f"{event_text}\n{status}"
    brief = await format_members_brief_list(front_members, lang)
    return f"{event_text}\n{status}\n\n{brief}"


async def format_member_info(member: dict[str, Any], lang: str = "ru") -> str:
    raw = json.loads(member.get("raw_json") or "{}")
    categories = await repo.get_categories_for_member(member["id"])
    custom_fields = await repo.get_custom_fields_map()

    parts: list[str] = []
    name = _clean_text(member.get("name")) or t("no_name", lang)
    parts.append(name)

    pronouns = _clean_text(member.get("pronouns"))
    if pronouns:
        parts.append(f"{t('pronouns', lang)}: {pronouns}")
    else:
        parts.append(f"{t('pronouns', lang)}: {t('not_specified', lang)}")

    if categories:
        parts.append(f"{t('categories', lang)}:\n" + "\n".join(f"- {cat}" for cat in categories))
    else:
        parts.append(f"{t('categories', lang)}:\n{t('not_specified', lang)}")

    description = await repo.replace_member_mentions(_clean_text(member.get("description")))
    if description:
        description_title = {"ru": "Описание", "en": "Description", "it": "Descrizione"}.get(lang, "Описание")
        parts.append(f"{description_title}:\n" + description)

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
            extra_title = {"ru": "Дополнительная информация", "en": "Additional info", "it": "Informazioni aggiuntive"}.get(lang, "Дополнительная информация")
            parts.append(f"{extra_title}:\n" + "\n\n".join(custom_parts))

    if member.get("is_archived"):
        reason = _clean_text(member.get("archived_reason"))
        parts.append(t("archive_yes", lang) + (f" ({reason})" if reason else ""))

    return "\n\n".join(parts)


async def format_front_info(front_members: list[dict[str, Any]], lang: str = "ru") -> str:
    if not front_members:
        empty_text = {
            "ru": "Сейчас: блюр\n\nНа фронте никого нет.",
            "en": "Now: blur\n\nNobody is in front.",
            "it": "Ora: blur\n\nNessuno e al fronte.",
        }.get(lang, "Сейчас: блюр\n\nНа фронте никого нет.")
        return empty_text

    title = {"ru": "Сейчас на фронте:", "en": "Currently in front:", "it": "Attualmente al fronte:"}.get(lang, "Сейчас на фронте:")
    chunks = [title]
    for member in front_members:
        chunks.append(await format_member_info(member, lang))
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
