from __future__ import annotations

import io
import re
import shutil
from datetime import datetime
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from loguru import logger
from pydantic import BaseModel, Field

from deepclaw.constant import workspace_path
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
    SKILLS_ROOT = workspace_path / "skills"

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

    def upload_skill_zip(self, *, file_name: str, data: bytes) -> SkillUploadResponse:
        if not data:
            raise ValueError("Uploaded zip file is empty.")
        if not file_name.lower().endswith(".zip"):
            raise ValueError("Only .zip skill packages are supported.")

        self.SKILLS_ROOT.mkdir(parents=True, exist_ok=True)
        members, skill_name = self._load_archive_members(file_name=file_name, data=data)
        target_dir = self.SKILLS_ROOT / skill_name
        if target_dir.exists():
            raise ValueError(
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
        self._sync_store_backend()
        return SkillUploadResponse(
            skill=self._build_skill_record(target_dir),
            extracted_files=extracted_files,
        )

    def delete_skill(self, *, skill_name: str) -> SkillDeleteResponse:
        normalized_name = self._normalize_skill_name(skill_name)
        target_dir = self.SKILLS_ROOT / normalized_name
        if not target_dir.exists() or not target_dir.is_dir():
            raise ValueError("Skill not found.")
        if not (target_dir / "SKILL.md").exists():
            raise ValueError("Target directory is not a valid skill.")

        shutil.rmtree(target_dir)
        logger.info("Skill deleted: {}", target_dir)
        self._sync_store_backend()
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
            raise ValueError("Invalid zip archive.") from exc

        with archive:
            file_infos = [
                info
                for info in archive.infolist()
                if not info.is_dir() and not info.filename.startswith("__MACOSX/")
            ]
            if not file_infos:
                raise ValueError("Zip archive does not contain any files.")

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
                raise ValueError("The zip root must contain SKILL.md.")

            members: list[tuple[Path, bytes]] = []
            for info, relative_path in zip(file_infos, relative_paths, strict=True):
                if not relative_path.parts:
                    continue
                members.append((relative_path, archive.read(info)))

        return members, skill_name

    def _validate_archive_path(self, raw_path: str) -> PurePosixPath:
        path = PurePosixPath(raw_path)
        if path.is_absolute():
            raise ValueError("Zip archive contains an absolute path, which is not allowed.")
        if any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("Zip archive contains an invalid path.")
        return path

    def _normalize_skill_name(self, skill_name: str) -> str:
        normalized = skill_name.strip().strip("/\\")
        if not normalized:
            raise ValueError("Skill name cannot be empty.")
        if normalized in {".", ".."}:
            raise ValueError("Invalid skill name.")
        normalized = re.sub(r"[\\/]+", "-", normalized)
        return normalized

    def _sync_store_backend(self) -> None:
        if settings.BACKEND_TYPE != "store":
            return
        try:
            from deepclaw.agents.general.agent import store
            from deepclaw.agents.general.utils import sync_skills_store
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to import store sync helpers: {}", exc)
            return

        if store is None:
            return
        # 仅在 store 后端启用时同步技能目录，避免管理层反向侵入核心逻辑。
        sync_skills_store(self.SKILLS_ROOT, store)


skill_manager = SkillManager()

