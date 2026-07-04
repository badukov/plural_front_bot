import json
import re
import time
from typing import Any

from app.i18n import t
from app.repository import repo


IMAGE_MD_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

EVENT_LABELS = {
    "initial": {"ru": "начальное состояние", "en": "initial state", "it": "stato iniziale"},
    "front_added": {"ru": "добавление", "en": "added", "it": "aggiunta"},
    "front_removed": {"ru": "снятие", "en": "removed", "it": "rimozione"},
    "front_replaced": {"ru": "замена фронта", "en": "front replaced", "it": "fronte sostituito"},
    "blur": {"ru": "блюр", "en": "blur", "it": "blur"},
    "florality_front_pulled": {"ru": "из Florality", "en": "from Florality", "it": "da Florality"},
}


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


def _event_label(event_type: str, lang: str) -> str:
    values = EVENT_LABELS.get(event_type)
    if not values:
        return event_type
    return values.get(lang) or values["ru"]


def _relative_time(ms: int, lang: str) -> str:
    seconds = max(0, int(time.time() - ms / 1000))
    units = [
        (24 * 60 * 60, {"ru": "дн.", "en": "d", "it": "g"}),
        (60 * 60, {"ru": "ч.", "en": "h", "it": "h"}),
        (60, {"ru": "мин.", "en": "min", "it": "min"}),
    ]
    for size, names in units:
        if seconds >= size:
            return f"{seconds // size} {names.get(lang, names['ru'])}"
    return {"ru": "только что", "en": "just now", "it": "adesso"}.get(lang, "только что")


def universal_time_text(ms: int, lang: str = "ru") -> str:
    utc_text = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ms / 1000))
    rel = _relative_time(ms, lang)
    if rel == "только что" or rel in {"just now", "adesso"}:
        return f"{utc_text} ({rel})"
    suffix = {"ru": "назад", "en": "ago", "it": "fa"}.get(lang, "назад")
    return f"{utc_text} ({rel} {suffix})"


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


def format_front_history(rows: list[dict[str, Any]], lang: str = "ru") -> str:
    if not rows:
        return t("history_empty", lang)

    lines = [t("history_title", lang)]
    for row in rows:
        members = row.get("members") or []
        names = [
            str(member.get("name") or "").strip()
            for member in members
            if isinstance(member, dict) and str(member.get("name") or "").strip()
        ]
        status = t("front_blur", lang) if not names else t("front_status", lang, names=", ".join(names))
        lines.append(
            f"{universal_time_text(int(row['created_at']), lang)}\n"
            f"{_event_label(str(row.get('event_type') or ''), lang)}: {status}"
        )
    return "\n\n".join(lines)


def format_front_statistics(stats: dict[str, Any], lang: str = "ru") -> str:
    lines = [t("stats_title", lang, days=stats["days"])]
    lines.append(t("stats_changes", lang, count=stats["changes"]))
    lines.append(t("stats_unique", lang, count=stats["unique_count"]))
    lines.append(t("stats_blur", lang, count=stats["blur_count"]))

    top_members = stats.get("top_members") or []
    if top_members:
        top_lines = [f"- {name}: {count}" for name, count in top_members]
        lines.append(t("stats_top", lang) + "\n" + "\n".join(top_lines))
    else:
        lines.append(t("stats_top", lang) + "\n-")

    busiest_day = stats.get("busiest_day")
    if busiest_day:
        lines.append(t("stats_busiest_day", lang, day=busiest_day[0], count=busiest_day[1]))

    last_change_at = int(stats.get("last_change_at") or 0)
    if last_change_at:
        lines.append(t("stats_last_change", lang, time=universal_time_text(last_change_at, lang)))
    return "\n\n".join(lines)


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
