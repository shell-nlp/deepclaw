from __future__ import annotations

import io
import re
import shutil
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

from loguru import logger
from pydantic import BaseModel, Field

from deepclaw.web_backend.common.errors import BusinessRuleError
from deepclaw.constant import WORKSPACE_PATH
from deepclaw.settings import settings


class SkillRecord(BaseModel):
    skill_name: str
    path: str
    description: str = ""
    file_count: int = 0
    created_at: str
    updated_at: str


class SkillListResponse(BaseModel):
    items: list[SkillRecord] = Field(default_factory=list)
    total: int = 0


class SkillUploadResponse(BaseModel):
    skill: SkillRecord
    extracted_files: int = 0


class SkillDeleteResponse(BaseModel):
    skill_name: str
    deleted_path: str


class SkillManager:
    SKILLS_ROOT = WORKSPACE_PATH / "skills"

    def __init__(self) -> None:
        self.SKILLS_ROOT.mkdir(parents=True, exist_ok=True)

    def list_skills(self, *, search: str = "") -> SkillListResponse:
        normalized_search = search.strip().lower()
        items: list[SkillRecord] = []

        for skill_dir in self._iter_skill_dirs():
            record = self._build_skill_record(skill_dir)
            if normalized_search and normalized_search not in (
                f"{record.skill_name}\n{record.description}".lower()
            ):
                continue
            items.append(record)

        items.sort(key=lambda item: item.updated_at, reverse=True)
        return SkillListResponse(items=items, total=len(items))

    async def upload_skill_zip(
        self,
        *,
        file_name: str,
        data: bytes,
        store: Any | None = None,
    ) -> SkillUploadResponse:
        """保存上传的技能包，并在 store 后端下同步到 LangGraph Store。

        Args:
            file_name: 上传文件名。
            data: 技能包压缩内容。
            store: 当前应用的 LangGraph Store，未提供时为 None。
        """
        if not data:
            raise BusinessRuleError("Uploaded zip file is empty.")
        if not file_name.lower().endswith(".zip"):
            raise BusinessRuleError("Only .zip skill packages are supported.")

        self.SKILLS_ROOT.mkdir(parents=True, exist_ok=True)
        members, skill_name = self._load_archive_members(file_name=file_name, data=data)
        target_dir = self.SKILLS_ROOT / skill_name
        if target_dir.exists():
            raise BusinessRuleError(
                f"Skill {skill_name!r} already exists. Delete it before uploading again."
            )

        extracted_files = 0
        try:
            for relative_path, content in members:
                destination = target_dir / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                extracted_files += 1
        except Exception:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise

        logger.info("Skill uploaded: {} -> {}", file_name, target_dir)
        await self._sync_store_backend(store)
        return SkillUploadResponse(
            skill=self._build_skill_record(target_dir),
            extracted_files=extracted_files,
        )

    async def delete_skill(
        self,
        *,
        skill_name: str,
        store: Any | None = None,
    ) -> SkillDeleteResponse:
        """删除技能包，并在 store 后端下同步到 LangGraph Store。

        Args:
            skill_name: 技能包名称。
            store: 当前应用的 LangGraph Store，未提供时为 None。
        """
        normalized_name = self._normalize_skill_name(skill_name)
        target_dir = self.SKILLS_ROOT / normalized_name
        if not target_dir.exists() or not target_dir.is_dir():
            raise BusinessRuleError("Skill not found.")
        if not (target_dir / "SKILL.md").exists():
            raise BusinessRuleError("Target directory is not a valid skill.")

        shutil.rmtree(target_dir)
        logger.info("Skill deleted: {}", target_dir)
        await self._sync_store_backend(store)
        return SkillDeleteResponse(
            skill_name=normalized_name,
            deleted_path=str(target_dir),
        )

    def _iter_skill_dirs(self) -> list[Path]:
        if not self.SKILLS_ROOT.exists():
            return []
        return [
            path
            for path in self.SKILLS_ROOT.iterdir()
            if path.is_dir() and (path / "SKILL.md").exists()
        ]

    def _build_skill_record(self, skill_dir: Path) -> SkillRecord:
        skill_md = skill_dir / "SKILL.md"
        stat = skill_dir.stat()
        description = self._extract_description(skill_md)
        file_count = sum(1 for path in skill_dir.rglob("*") if path.is_file())
        return SkillRecord(
            skill_name=skill_dir.name,
            path=str(skill_dir),
            description=description,
            file_count=file_count,
            created_at=datetime.fromtimestamp(stat.st_ctime).isoformat(),
            updated_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        )

    def _extract_description(self, skill_md: Path) -> str:
        try:
            text = skill_md.read_text(encoding="utf-8")
        except Exception:
            return ""

        for line in text.splitlines():
            normalized = line.strip()
            if not normalized or normalized.startswith("#"):
                continue
            return normalized[:240]
        return ""

    def _load_archive_members(
        self, *, file_name: str, data: bytes
    ) -> tuple[list[tuple[Path, bytes]], str]:
        try:
            archive = ZipFile(io.BytesIO(data))
        except Exception as exc:
            raise BusinessRuleError("Invalid zip archive.") from exc

        with archive:
            file_infos = [
                info
                for info in archive.infolist()
                if not info.is_dir() and not info.filename.startswith("__MACOSX/")
            ]
            if not file_infos:
                raise BusinessRuleError("Zip archive does not contain any files.")

            member_paths = [self._validate_archive_path(info.filename) for info in file_infos]
            top_levels = {path.parts[0] for path in member_paths if path.parts}
            has_single_root = len(top_levels) == 1 and all(
                len(path.parts) > 1 for path in member_paths
            )

            if has_single_root:
                archive_root = next(iter(top_levels))
                relative_paths = [Path(*path.parts[1:]) for path in member_paths]
                skill_name = self._normalize_skill_name(archive_root)
            else:
                relative_paths = [Path(*path.parts) for path in member_paths]
                skill_name = self._normalize_skill_name(Path(file_name).stem)

            if not any(path == Path("SKILL.md") for path in relative_paths):
                raise BusinessRuleError("The zip root must contain SKILL.md.")

            members: list[tuple[Path, bytes]] = []
            for info, relative_path in zip(file_infos, relative_paths, strict=True):
                if not relative_path.parts:
                    continue
                members.append((relative_path, archive.read(info)))

        return members, skill_name

    def _validate_archive_path(self, raw_path: str) -> PurePosixPath:
        path = PurePosixPath(raw_path)
        if path.is_absolute():
            raise BusinessRuleError("Zip archive contains an absolute path, which is not allowed.")
        if any(part in {"", ".", ".."} for part in path.parts):
            raise BusinessRuleError("Zip archive contains an invalid path.")
        return path

    def _normalize_skill_name(self, skill_name: str) -> str:
        normalized = skill_name.strip().strip("/\\")
        if not normalized:
            raise BusinessRuleError("Skill name cannot be empty.")
        if normalized in {".", ".."}:
            raise BusinessRuleError("Invalid skill name.")
        normalized = re.sub(r"[\\/]+", "-", normalized)
        return normalized

    async def _sync_store_backend(self, store: Any | None) -> None:
        """在 store 后端下把技能目录重新同步到 LangGraph Store。

        Args:
            store: 当前应用的 LangGraph Store，未提供时为 None。
        """
        if settings.BACKEND_TYPE != "store" or store is None:
            return
        # 仅在 store 后端启用时同步技能目录，避免管理层反向侵入核心逻辑。
        from deepclaw.agents.general.utils import sync_skills_store

        await sync_skills_store(self.SKILLS_ROOT, store)


skill_manager = SkillManager()

