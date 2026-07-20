import asyncio
import hashlib
import json
import logging
import unicodedata
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from aiogram import Bot
from PIL import Image

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
    imported_names: tuple[str, ...] = field(default_factory=tuple)
    changed_names: tuple[str, ...] = field(default_factory=tuple)
    missing_local_names: tuple[str, ...] = field(default_factory=tuple)
    missing_remote_names: tuple[str, ...] = field(default_factory=tuple)
    unchanged: int = 0
    skipped: int = 0
    backup_path: str = ""

    @property
    def imported(self) -> int:
        return len(self.imported_names)

    @property
    def changed(self) -> int:
        return len(self.changed_names)

    @property
    def missing_local(self) -> int:
        return len(self.missing_local_names)

    @property
    def missing_remote(self) -> int:
        return len(self.missing_remote_names)


@dataclass(frozen=True)
class FloralityAvatarSyncResult:
    downloaded_names: tuple[str, ...] = field(default_factory=tuple)
    failed_names: tuple[str, ...] = field(default_factory=tuple)
    failed_remote_ids: tuple[str, ...] = field(default_factory=tuple)
    skipped_existing: int = 0
    skipped_ambiguous: int = 0
    skipped_missing_local: int = 0
    no_avatar: int = 0
    remaining: int = 0


@dataclass(frozen=True)
class FloralityCategorySyncResult:
    processed_groups: int = 0
    matched_groups: int = 0
    unmatched_groups: int = 0
    added_links: int = 0
    affected_names: tuple[str, ...] = field(default_factory=tuple)
    failed_group_names: tuple[str, ...] = field(default_factory=tuple)
    remaining: int = 0
    next_offset: int = 0
    backup_path: str = ""


def _normalized_name(value: object) -> str:
    return str(value or "").strip().casefold()


def _normalized_path(parts: list[object]) -> tuple[str, ...]:
    normalized: list[str] = []
    for part in parts:
        value = unicodedata.normalize("NFKC", str(part or ""))
        value = " ".join(value.split()).casefold()
        if value:
            normalized.append(value)
    return tuple(normalized)


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
        self._avatar_sync_lock = asyncio.Lock()
        self._category_sync_lock = asyncio.Lock()

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

    async def list_groups(self) -> list[dict[str, Any]] | None:
        data = await self._request("GET", "/groups")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return None

    async def get_group_layout(self, group_id: str) -> list[dict[str, Any]] | None:
        data = await self._request("GET", f"/groups/{group_id}/layout")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return None

    async def _download_member_avatar(self, remote_member: dict[str, Any], remote_id: str) -> str:
        avatar_path = str(remote_member.get("avatarUrl") or "").strip()
        if not avatar_path:
            return ""

        try:
            return await asyncio.to_thread(self._download_member_avatar_sync, avatar_path, remote_id)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            logger.warning("Florality avatar download failed for remote member %s: %s", remote_id, error)
            return ""

    def _download_member_avatar_sync(self, avatar_path: str, remote_id: str) -> str:
        parsed_base = urlsplit(self.base_url)
        origin = f"{parsed_base.scheme}://{parsed_base.netloc}/"
        avatar_url = urljoin(origin, avatar_path)
        request = Request(
            avatar_url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "image/*",
                "User-Agent": "plural-front-bot/1.0",
            },
            method="GET",
        )
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type()
            if not content_type.startswith("image/"):
                raise OSError(f"unexpected avatar content type: {content_type}")
            data = response.read(10 * 1024 * 1024 + 1)
        if not data or len(data) > 10 * 1024 * 1024:
            raise OSError("avatar is empty or exceeds 10 MiB")

        with Image.open(BytesIO(data)) as source:
            source.seek(0)
            image = source.convert("RGBA")
            if image.width + image.height > 10000:
                image.thumbnail((5000, 5000))
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
            encoded = BytesIO()
            background.save(encoded, format="JPEG", quality=90, optimize=True)
            jpeg_data = encoded.getvalue()

        digest = hashlib.sha256(remote_id.encode("utf-8")).hexdigest()[:24]
        avatar_dir = settings.database_path.parent / "avatars" / PROVIDER
        avatar_dir.mkdir(parents=True, exist_ok=True)
        avatar_file = avatar_dir / f"{digest}.jpg"
        temporary_file = avatar_file.with_suffix(f"{avatar_file.suffix}.tmp")
        temporary_file.write_bytes(jpeg_data)
        temporary_file.replace(avatar_file)
        # Store an absolute path so Telegram delivery does not depend on the
        # process working directory used by systemd on the VPS.
        return str(avatar_file.resolve())

    @staticmethod
    def _has_usable_avatar(member: dict[str, Any]) -> bool:
        value = str(member.get("avatar_url") or "").strip()
        if not value:
            return False
        if value.startswith(("http://", "https://")):
            return True
        path = Path(value)
        return path.is_file() and path.suffix.casefold() in {".jpg", ".jpeg"}

    async def sync_member_avatars_from_florality(
        self,
        excluded_remote_ids: set[str] | None = None,
    ) -> FloralityAvatarSyncResult:
        if not self.enabled:
            return FloralityAvatarSyncResult()

        async with self._avatar_sync_lock:
            excluded_remote_ids = excluded_remote_ids or set()
            remote_members = await self.list_members()
            if remote_members is None:
                return FloralityAvatarSyncResult(failed_names=("Florality API",))

            candidates: list[tuple[dict[str, Any], str, str]] = []
            skipped_existing = 0
            skipped_ambiguous = 0
            skipped_missing_local = 0
            no_avatar = 0

            for remote_member in remote_members:
                remote_id = _remote_member_id(remote_member)
                if not remote_id:
                    continue
                if not str(remote_member.get("avatarUrl") or "").strip():
                    no_avatar += 1
                    continue
                if remote_id in excluded_remote_ids:
                    continue

                local_id = await repo.get_local_id_for_external_id(PROVIDER, MEMBER_ENTITY, remote_id)
                local_member = await repo.get_member_by_id(local_id) if local_id else None
                if not local_member:
                    matches = await repo.find_members_by_names(
                        [
                            str(remote_member.get("name") or "").strip(),
                            str(remote_member.get("displayName") or "").strip(),
                        ]
                    )
                    if len({member["id"] for member in matches}) > 1:
                        skipped_ambiguous += 1
                        continue
                    local_member = matches[0] if matches else None
                    if local_member:
                        await repo.set_external_id(PROVIDER, MEMBER_ENTITY, str(local_member["id"]), remote_id)
                if not local_member:
                    skipped_missing_local += 1
                    continue
                if self._has_usable_avatar(local_member):
                    skipped_existing += 1
                    continue

                name = str(remote_member.get("name") or remote_member.get("displayName") or remote_id).strip()
                candidates.append((remote_member, str(local_member["id"]), name))

            batch_size = settings.florality_avatar_batch_size
            downloaded_names: list[str] = []
            failed_names: list[str] = []
            failed_remote_ids: list[str] = []
            batch = candidates[:batch_size]
            for index, (remote_member, local_id, name) in enumerate(batch):
                remote_id = _remote_member_id(remote_member)
                avatar_path = await self._download_member_avatar(remote_member, str(remote_id or ""))
                if avatar_path and await repo.update_member_avatar_url(local_id, avatar_path):
                    downloaded_names.append(name)
                else:
                    failed_names.append(name)
                    if remote_id:
                        failed_remote_ids.append(remote_id)
                if index + 1 < len(batch):
                    await asyncio.sleep(settings.florality_avatar_delay_seconds)

            return FloralityAvatarSyncResult(
                downloaded_names=tuple(downloaded_names),
                failed_names=tuple(failed_names),
                failed_remote_ids=tuple(failed_remote_ids),
                skipped_existing=skipped_existing,
                skipped_ambiguous=skipped_ambiguous,
                skipped_missing_local=skipped_missing_local,
                no_avatar=no_avatar,
                remaining=max(0, len(candidates) - len(batch)) + len(failed_names),
            )

    @staticmethod
    def _remote_group_paths(groups: list[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
        groups_by_id = {
            str(group.get("_id") or group.get("id")): group
            for group in groups
            if group.get("_id") or group.get("id")
        }
        paths: dict[str, tuple[str, ...]] = {}
        for group_id, group in groups_by_id.items():
            # The canonical root has no parent and is not a local category.
            if not group.get("parentId"):
                continue
            parts: list[object] = [group.get("name")]
            parent_id = str(group.get("parentId") or "")
            seen = {group_id}
            while parent_id and parent_id in groups_by_id and parent_id not in seen:
                seen.add(parent_id)
                parent = groups_by_id[parent_id]
                # Do not include Florality's canonical "Root" node in paths.
                if not parent.get("parentId"):
                    break
                parts.append(parent.get("name"))
                parent_id = str(parent.get("parentId") or "")
            path = _normalized_path(list(reversed(parts)))
            if path:
                paths[group_id] = path
        return paths

    @staticmethod
    def _local_group_paths(groups: list[dict[str, Any]]) -> dict[tuple[str, ...], str]:
        groups_by_id = {str(group.get("id")): group for group in groups if group.get("id")}
        ids_by_path: dict[tuple[str, ...], list[str]] = {}
        for group_id, group in groups_by_id.items():
            parts: list[object] = [group.get("name")]
            parent_id = str(group.get("parent_id") or "")
            seen = {group_id}
            while parent_id and parent_id != "root" and parent_id in groups_by_id and parent_id not in seen:
                seen.add(parent_id)
                parent = groups_by_id[parent_id]
                parts.append(parent.get("name"))
                parent_id = str(parent.get("parent_id") or "")
            path = _normalized_path(list(reversed(parts)))
            if path:
                ids_by_path.setdefault(path, []).append(group_id)
        # A duplicate full path is unsafe to assign automatically.
        return {path: ids[0] for path, ids in ids_by_path.items() if len(ids) == 1}

    async def sync_imported_member_categories_from_florality(
        self,
        offset: int = 0,
    ) -> FloralityCategorySyncResult:
        """Add Florality layout categories to members created by the Florality import.

        Existing links are preserved, no links are removed, and no Florality data is
        mutated. Work is intentionally paged to stay comfortably below API limits.
        """
        if not self.enabled:
            return FloralityCategorySyncResult()

        async with self._category_sync_lock:
            remote_groups = await self.list_groups()
            if remote_groups is None:
                return FloralityCategorySyncResult(failed_group_names=("Florality API",))

            local_groups = await repo.get_all_groups()
            remote_paths = self._remote_group_paths(remote_groups)
            local_ids_by_path = self._local_group_paths(local_groups)
            remote_names = {
                str(group.get("_id") or group.get("id")): str(group.get("name") or "")
                for group in remote_groups
                if group.get("_id") or group.get("id")
            }
            candidates = sorted(
                (
                    (path, remote_id, local_ids_by_path[path])
                    for remote_id, path in remote_paths.items()
                    if path in local_ids_by_path
                ),
                key=lambda item: (item[0], item[1]),
            )

            imported_by_remote_id: dict[str, tuple[str, str]] = {}
            mappings = await repo.get_external_id_mappings(PROVIDER, MEMBER_ENTITY)
            for mapping in mappings:
                local_id = str(mapping.get("local_id") or "")
                remote_id = str(mapping.get("remote_id") or "")
                if not local_id or not remote_id:
                    continue
                member = await repo.get_member_by_id(local_id)
                if not member:
                    continue
                try:
                    raw = json.loads(member.get("raw_json") or "{}")
                except json.JSONDecodeError:
                    raw = {}
                florality_meta = raw.get("florality") if isinstance(raw, dict) else None
                if not isinstance(florality_meta, dict) or str(florality_meta.get("_id") or "") != remote_id:
                    continue
                imported_by_remote_id[remote_id] = (local_id, str(member.get("name") or local_id))

            safe_offset = min(max(0, offset), len(candidates))
            batch_size = settings.florality_category_batch_size
            batch = candidates[safe_offset : safe_offset + batch_size]
            links: list[tuple[str, str]] = []
            failed_group_names: list[str] = []
            for index, (_path, remote_group_id, local_group_id) in enumerate(batch):
                layout = await self.get_group_layout(remote_group_id)
                if layout is None:
                    failed_group_names.append(remote_names.get(remote_group_id) or remote_group_id)
                else:
                    for entry in layout:
                        if entry.get("type") != "member":
                            continue
                        imported = imported_by_remote_id.get(str(entry.get("memberId") or ""))
                        if imported:
                            links.append((imported[0], local_group_id))
                if index + 1 < len(batch):
                    await asyncio.sleep(settings.florality_category_delay_seconds)

            if failed_group_names:
                return FloralityCategorySyncResult(
                    processed_groups=len(batch) - len(failed_group_names),
                    matched_groups=len(candidates),
                    unmatched_groups=max(0, len(remote_paths) - len(candidates)),
                    failed_group_names=tuple(failed_group_names),
                    remaining=max(0, len(candidates) - safe_offset),
                    next_offset=safe_offset,
                )

            backup_path = ""
            added_count = 0
            affected_ids: set[str] = set()
            missing_links = await repo.get_missing_member_group_links(links)
            if missing_links:
                backup = await create_database_backup("florality_categories")
                backup_path = str(backup)
                added_count, affected_ids = await repo.add_member_group_links(missing_links)

            next_offset = safe_offset + len(batch)
            remaining = max(0, len(candidates) - next_offset)
            if not remaining:
                next_offset = 0
            affected_names = sorted(
                imported_by_remote_id[remote_id][1]
                for remote_id in imported_by_remote_id
                if imported_by_remote_id[remote_id][0] in affected_ids
            )
            return FloralityCategorySyncResult(
                processed_groups=len(batch),
                matched_groups=len(candidates),
                unmatched_groups=max(0, len(remote_paths) - len(candidates)),
                added_links=added_count,
                affected_names=tuple(affected_names),
                remaining=remaining,
                next_offset=next_offset,
                backup_path=backup_path,
            )

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
            import_payload = dict(remote_member)
            local_avatar_path = await self._download_member_avatar(remote_member, remote_id)
            if local_avatar_path:
                import_payload["_local_avatar_path"] = local_avatar_path
            member, _action = await repo.upsert_florality_member(import_payload, remote_id)
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

        backup_path = ""
        imported_names: list[str] = []
        changed_names: list[str] = []
        missing_local_names: list[str] = []
        missing_remote_names: list[str] = []
        unchanged = 0
        skipped = 0
        active_remote_ids: set[str] = set()

        async def ensure_backup() -> None:
            nonlocal backup_path
            if backup_path:
                return
            backup = await create_database_backup("florality_import")
            backup_path = str(backup)
            logger.info("Database backup created before Florality import: %s", backup.name)

        for remote_member in remote_members:
            remote_id = _remote_member_id(remote_member)
            if not remote_id:
                skipped += 1
                continue
            active_remote_ids.add(remote_id)

            name = str(remote_member.get("name") or remote_member.get("displayName") or remote_id).strip()
            local_member, action = await repo.compare_florality_member(remote_member, remote_id)
            if local_member:
                mapped_local_id = await repo.get_local_id_for_external_id(PROVIDER, MEMBER_ENTITY, remote_id)
                if mapped_local_id != str(local_member["id"]):
                    await ensure_backup()
                    await repo.set_external_id(PROVIDER, MEMBER_ENTITY, str(local_member["id"]), remote_id)
            if action == "unchanged":
                unchanged += 1
            elif action == "changed":
                changed_names.append(name)
            elif action == "missing":
                await ensure_backup()
                imported_member = await self.import_member_from_florality(remote_member, create_backup=False)
                if imported_member:
                    imported_names.append(imported_member["name"])
                else:
                    missing_local_names.append(name)
                    skipped += 1
            elif action == "ambiguous":
                skipped += 1
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
            imported_names=tuple(imported_names),
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
                if changed:
                    await repo.record_current_front_history("florality_front_pulled", created_by=None)
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


async def sync_florality_member_avatars(
    excluded_remote_ids: set[str] | None = None,
) -> FloralityAvatarSyncResult:
    return await florality.sync_member_avatars_from_florality(excluded_remote_ids)


async def sync_florality_imported_member_categories(offset: int = 0) -> FloralityCategorySyncResult:
    return await florality.sync_imported_member_categories_from_florality(offset)


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
