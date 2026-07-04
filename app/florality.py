import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aiogram import Bot

from app.backups import create_database_backup
from app.broadcast import broadcast_by_language
from app.config import settings
from app.formatters import format_front_notification
from app.i18n import t
from app.repository import repo


PROVIDER = "florality"
MEMBER_ENTITY = "member"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FloralityImportResult:
    imported_front_names: tuple[str, ...] = field(default_factory=tuple)
    changed_names: tuple[str, ...] = field(default_factory=tuple)
    missing_local_names: tuple[str, ...] = field(default_factory=tuple)
    missing_remote_names: tuple[str, ...] = field(default_factory=tuple)
    unchanged: int = 0
    skipped: int = 0
    backup_path: str = ""

    @property
    def imported_front(self) -> int:
        return len(self.imported_front_names)

    @property
    def changed(self) -> int:
        return len(self.changed_names)

    @property
    def missing_local(self) -> int:
        return len(self.missing_local_names)

    @property
    def missing_remote(self) -> int:
        return len(self.missing_remote_names)


def _normalized_name(value: object) -> str:
    return str(value or "").strip().casefold()


def _remote_member_id(member: dict[str, Any]) -> str | None:
    value = member.get("_id") or member.get("id")
    return str(value) if value else None


class FloralityClient:
    def __init__(self) -> None:
        self.base_url = settings.florality_api_base_url
        self.token = settings.florality_api_token
        self._front_read_forbidden = False
        self._front_write_forbidden = False
        self._front_lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(settings.florality_sync_enabled and self.token and self.base_url)

    @property
    def front_enabled(self) -> bool:
        return bool(self.enabled and settings.florality_sync_front_enabled and not self._front_write_forbidden)

    @property
    def front_pull_enabled(self) -> bool:
        return bool(self.enabled and settings.florality_pull_front_enabled and not self._front_read_forbidden)

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        if not self.enabled:
            return None

        return await asyncio.to_thread(self._request_sync, method, path, payload)

    def _request_sync(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        body = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "plural-front-bot/1.0",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except HTTPError as error:
            code, message = self._read_error(error)
            if error.code == 403 and path.startswith("/front"):
                if method == "GET":
                    self._front_read_forbidden = True
                    logger.warning(
                        "Florality front pull disabled until restart: %s %s -> HTTP 403 (%s: %s)",
                        method,
                        path,
                        code,
                        message,
                    )
                else:
                    self._front_write_forbidden = True
                    logger.warning(
                        "Florality front push disabled until restart: %s %s -> HTTP 403 (%s: %s)",
                        method,
                        path,
                        code,
                        message,
                    )
            else:
                logger.warning(
                    "Florality request failed: %s %s -> HTTP %s (%s: %s)",
                    method,
                    path,
                    error.code,
                    code,
                    message,
                )
            return None
        except URLError as error:
            logger.warning("Florality request failed: %s %s -> %s", method, path, error.reason)
            return None
        except TimeoutError:
            logger.warning("Florality request timed out: %s %s", method, path)
            return None
        except json.JSONDecodeError:
            logger.warning("Florality response was not valid JSON: %s %s", method, path)
            return None

    def _read_error(self, error: HTTPError) -> tuple[str, str]:
        try:
            raw = error.read()
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            data = {}

        code = str(data.get("code") or "HTTP_ERROR") if isinstance(data, dict) else "HTTP_ERROR"
        message = str(data.get("message") or "No JSON error message") if isinstance(data, dict) else "No JSON error message"
        return code[:80], message[:240]

    async def list_members(self) -> list[dict[str, Any]] | None:
        data = await self._request("GET", "/members")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return None

    async def import_member_from_florality(
        self,
        remote_member: dict[str, Any],
        create_backup: bool = False,
    ) -> dict[str, Any] | None:
        remote_id = _remote_member_id(remote_member)
        if not remote_id:
            logger.warning("Florality member import skipped: remote id is missing")
            return None
        try:
            if create_backup:
                backup_path = await create_database_backup("florality_front_import")
                logger.info("Database backup created before Florality front import: %s", backup_path.name)
            member, _action = await repo.upsert_florality_member(remote_member, remote_id)
            return member
        except ValueError:
            logger.warning("Florality member import skipped: required fields are missing")
            return None
        except Exception:
            logger.exception("Unexpected Florality member import error")
            return None

    async def import_members_from_florality(self) -> FloralityImportResult:
        if not self.enabled:
            return FloralityImportResult()

        remote_members = await self.list_members()
        if remote_members is None:
            return FloralityImportResult(skipped=1)

        remote_front_members = await self.get_front()
        remote_front_ids = {
            remote_id
            for member in remote_front_members or []
            if (remote_id := _remote_member_id(member))
        }
        backup_path = ""
        imported_front_names: list[str] = []
        changed_names: list[str] = []
        missing_local_names: list[str] = []
        missing_remote_names: list[str] = []
        unchanged = 0
        skipped = 0
        active_remote_ids: set[str] = set()

        for remote_member in remote_members:
            remote_id = _remote_member_id(remote_member)
            if not remote_id:
                skipped += 1
                continue
            active_remote_ids.add(remote_id)

            name = str(remote_member.get("name") or remote_member.get("displayName") or remote_id).strip()
            _local_member, action = await repo.compare_florality_member(remote_member, remote_id)
            if action == "unchanged":
                unchanged += 1
            elif action == "changed":
                changed_names.append(name)
            elif action == "missing" and remote_id in remote_front_ids:
                if not backup_path:
                    backup = await create_database_backup("florality_front_import")
                    backup_path = str(backup)
                    logger.info("Database backup created before Florality front import: %s", backup.name)
                imported_member = await self.import_member_from_florality(remote_member, create_backup=False)
                if imported_member:
                    imported_front_names.append(imported_member["name"])
                else:
                    skipped += 1
            elif action == "missing":
                continue
            else:
                skipped += 1

        deleted_ids = await repo.get_deleted_member_ids()
        mappings = await repo.get_external_id_mappings(PROVIDER, MEMBER_ENTITY)
        for mapping in mappings:
            local_id = str(mapping.get("local_id") or "")
            remote_id = str(mapping.get("remote_id") or "")
            if not local_id or not remote_id or remote_id in active_remote_ids or local_id in deleted_ids:
                continue
            member = await repo.get_member_by_id(local_id)
            if not member:
                continue
            missing_remote_names.append(str(member.get("name") or local_id))

        return FloralityImportResult(
            imported_front_names=tuple(imported_front_names),
            changed_names=tuple(changed_names),
            missing_local_names=tuple(missing_local_names),
            missing_remote_names=tuple(missing_remote_names),
            unchanged=unchanged,
            skipped=skipped,
            backup_path=backup_path,
        )

    async def get_front(self) -> list[dict[str, Any]] | None:
        if not self.front_pull_enabled:
            return None

        data = await self._request("GET", "/front")
        if not isinstance(data, dict):
            return None

        member_ids = data.get("memberIds") or []
        members = data.get("members") or []
        if not isinstance(member_ids, list) or not isinstance(members, list):
            logger.warning("Florality front pull skipped: unexpected response shape")
            return None

        members_by_id = {
            remote_id: member
            for member in members
            if isinstance(member, dict) and (remote_id := _remote_member_id(member))
        }
        result = []
        for remote_id in [str(value) for value in member_ids if value]:
            result.append(members_by_id.get(remote_id, {"_id": remote_id}))
        return result

    async def _find_remote_member(
        self,
        local_member: dict[str, Any],
        remote_members: list[dict[str, Any]],
    ) -> tuple[str | None, bool]:
        name = _normalized_name(local_member.get("name"))
        if not name:
            return None, False

        matches = []
        for member in remote_members:
            remote_name = _normalized_name(member.get("name"))
            remote_display_name = _normalized_name(member.get("displayName"))
            if name in {remote_name, remote_display_name}:
                remote_id = _remote_member_id(member)
                if remote_id:
                    matches.append(remote_id)

        unique_matches = sorted(set(matches))
        if len(unique_matches) == 1:
            return unique_matches[0], False
        if len(unique_matches) > 1:
            logger.warning("Florality member mapping skipped: duplicate remote names for local id %s", local_member.get("id"))
            return None, True
        return None, False

    async def ensure_member(
        self,
        local_member: dict[str, Any],
        remote_members: list[dict[str, Any]] | None = None,
        create_missing: bool | None = None,
    ) -> str | None:
        if not self.enabled:
            return None

        local_id = str(local_member.get("id") or "")
        if not local_id:
            return None

        mapped_id = await repo.get_external_id(PROVIDER, MEMBER_ENTITY, local_id)
        if mapped_id:
            return mapped_id

        remote_members = remote_members if remote_members is not None else await self.list_members()
        if remote_members is None:
            logger.warning("Florality member sync skipped: remote members list unavailable")
            return None

        remote_id, has_duplicates = await self._find_remote_member(local_member, remote_members)
        if remote_id:
            await repo.set_external_id(PROVIDER, MEMBER_ENTITY, local_id, remote_id)
            return remote_id
        if has_duplicates:
            return None

        if create_missing is None:
            create_missing = settings.florality_create_missing_members_enabled
        if not create_missing:
            logger.warning("Florality member creation disabled for local id %s", local_id)
            return None

        payload = {
            "name": str(local_member.get("name") or "").strip(),
        }
        pronouns = str(local_member.get("pronouns") or "").strip()
        description = str(local_member.get("description") or "").strip()
        if pronouns:
            payload["pronouns"] = pronouns
        if description:
            payload["about"] = description

        if not payload["name"]:
            return None

        created = await self._request("POST", "/members", payload)
        if isinstance(created, dict):
            remote_id = _remote_member_id(created)
            if remote_id:
                await repo.set_external_id(PROVIDER, MEMBER_ENTITY, local_id, remote_id)
                return remote_id

        logger.warning("Florality member creation skipped or failed for local id %s", local_id)
        return None

    async def sync_created_member(self, local_member: dict[str, Any]) -> None:
        if not self.enabled:
            return
        try:
            await self.ensure_member(
                local_member,
                create_missing=settings.florality_create_missing_members_enabled,
            )
        except Exception:
            logger.exception("Unexpected Florality member sync error")

    async def sync_front(self, front_members: list[dict[str, Any]]) -> None:
        if not self.front_enabled:
            return

        try:
            async with self._front_lock:
                if not front_members:
                    await self._request("DELETE", "/front")
                    return

                remote_members = await self.list_members()
                if remote_members is None:
                    logger.warning("Florality front sync skipped: remote members list unavailable")
                    return

                remote_ids: list[str] = []
                for member in front_members:
                    remote_id = await self.ensure_member(
                        member,
                        remote_members,
                        create_missing=settings.florality_create_missing_members_enabled,
                    )
                    if not remote_id:
                        logger.warning("Florality front sync skipped: member mapping failed for local id %s", member.get("id"))
                        return
                    if remote_id not in remote_ids:
                        remote_ids.append(remote_id)

                await self._request("DELETE", "/front")
                for remote_id in remote_ids:
                    await self._request(
                        "POST",
                        "/front/members",
                        {"memberId": remote_id},
                    )
        except Exception:
            logger.exception("Unexpected Florality front sync error")

    async def _resolve_local_front_member(self, remote_member: dict[str, Any]) -> dict[str, Any] | None:
        remote_id = _remote_member_id(remote_member)
        if remote_id:
            local_id = await repo.get_local_id_for_external_id(PROVIDER, MEMBER_ENTITY, remote_id)
            if local_id:
                local_member = await repo.get_member_by_id(local_id)
                if local_member and local_id not in await repo.get_deleted_member_ids():
                    return local_member

        names = [
            str(remote_member.get("name") or "").strip(),
            str(remote_member.get("displayName") or "").strip(),
        ]
        local_member = await repo.find_unique_member_by_names(names)
        if local_member and remote_id:
            await repo.set_external_id(PROVIDER, MEMBER_ENTITY, local_member["id"], remote_id)
        return local_member

    async def pull_front_to_local(self) -> tuple[bool, list[dict[str, Any]]]:
        if not self.front_pull_enabled:
            return False, []

        try:
            async with self._front_lock:
                remote_front_members = await self.get_front()
                if remote_front_members is None:
                    return False, []

                local_ids: list[str] = []
                for remote_member in remote_front_members:
                    local_member = await self._resolve_local_front_member(remote_member)
                    if not local_member:
                        local_member = await self.import_member_from_florality(remote_member, create_backup=True)
                    if not local_member:
                        logger.warning(
                            "Florality front pull skipped: remote member is not mapped to a local member"
                        )
                        return False, []
                    local_ids.append(local_member["id"])

                changed = await repo.replace_front_members(
                    local_ids,
                    created_by=None,
                    event_type="florality_front_pulled",
                    details={"provider": PROVIDER, "front_count": len(local_ids)},
                )
                return changed, await repo.get_current_front_members()
        except Exception:
            logger.exception("Unexpected Florality front pull error")
            return False, []


florality = FloralityClient()


async def sync_florality_member(member: dict[str, Any]) -> None:
    await florality.sync_created_member(member)


async def sync_florality_front(front_members: list[dict[str, Any]]) -> None:
    await florality.sync_front(front_members)


async def import_florality_members() -> FloralityImportResult:
    return await florality.import_members_from_florality()


async def run_florality_front_pull(bot: Bot) -> None:
    if not florality.front_pull_enabled:
        return

    interval = settings.florality_pull_interval_seconds
    logger.info("Florality front pull started with %s second interval", interval)
    while True:
        await asyncio.sleep(interval)
        changed, front_members = await florality.pull_front_to_local()
        if changed:
            await broadcast_by_language(
                bot,
                lambda lang: format_front_notification(
                    t("front_changed_florality_event", lang),
                    front_members,
                    lang,
                ),
            )
