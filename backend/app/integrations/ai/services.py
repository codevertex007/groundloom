"""Authorized backend implementation of the AI service port."""

from dataclasses import dataclass
from typing import Any

from groundloom_harness.skills_backend import SkillPackage
from sqlalchemy.orm import Session

from ...config import Settings
from ...context import RuntimeContext
from ...errors import GroundloomError
from ...models import Skill, SkillVersion
from ...schemas import PatchCreate, PatchOperation
from ...services import (
    content_blocks,
    create_patch,
    list_skills,
    project_detail,
    read_memory,
    read_passage,
    validate_content,
    validation_dto,
)
from .retrieval import search_evidence


@dataclass(frozen=True)
class GroundloomAgentServices:
    """Bind trusted tenant/project context once, outside model arguments."""

    db: Session
    context: RuntimeContext
    project_id: str
    settings: Settings

    def project_snapshot(self) -> dict[str, Any]:
        return project_detail(self.db, self.context, self.project_id)

    def project_skills(self) -> list[dict[str, Any]]:
        selected = set(self.project_snapshot()["config"].get("skill_version_ids", []))
        return [
            skill
            for skill in list_skills(self.db, self.context)
            if any(version["id"] in selected for version in skill["versions"])
        ]

    def search_source_passages(self, query: str, limit: int = 8) -> dict[str, Any]:
        return search_evidence(
            self.db,
            self.context,
            self.project_id,
            query,
            limit=limit,
            settings=self.settings,
        ).model_dump()

    def read_source_passage(self, source_version_id: str, passage_id: str) -> dict[str, Any]:
        allowed = set(self.project_snapshot()["config"].get("source_version_ids", []))
        if source_version_id not in allowed:
            raise GroundloomError(
                "PERMISSION_DENIED",
                "The passage is outside the project source scope.",
                403,
            )
        return read_passage(self.db, self.context, source_version_id, passage_id)

    def read_current_content(self) -> dict[str, Any]:
        version, blocks = content_blocks(self.db, self.context, self.project_id)
        return {
            "version_id": version.id,
            "version_no": version.version_no,
            "blocks": [
                {
                    "id": block.id,
                    "type": block.block_type,
                    "payload": block.payload,
                    "citations": block.citations,
                }
                for block in blocks
            ],
        }

    def validate_current_content(self) -> dict[str, Any]:
        validation = validate_content(self.db, self.context, self.project_id)
        return validation_dto(self.db, validation)

    def propose_text_patch(
        self,
        summary: str,
        text: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        version, blocks = content_blocks(self.db, self.context, self.project_id)
        operation = PatchOperation(
            op="insert_after",
            after_block_id=blocks[-1].id if blocks else None,
            payload={"block_type": "paragraph", "text": text[:20_000]},
            citations=(citations or [])[:20],
        )
        patch = create_patch(
            self.db,
            self.context,
            self.project_id,
            PatchCreate(
                base_content_version_id=version.id,
                operations=[operation],
                summary=summary[:2_000],
                idempotency_key=(
                    f"deepagents:{self.context.workspace_id}:"
                    f"{self.project_id}:{version.id}:{summary[:80]}"
                ),
            ),
        )
        return {"patch_id": patch.id, "status": patch.status}

    def read_workspace_memory(self) -> list[dict[str, Any]]:
        return read_memory(self.db, self.context)

    def list_packages(self) -> tuple[SkillPackage, ...]:
        selected = set(self.project_snapshot()["config"].get("skill_version_ids", []))
        if not selected:
            return ()
        rows = (
            self.db.query(SkillVersion, Skill)
            .join(Skill, Skill.id == SkillVersion.skill_id)
            .filter(
                SkillVersion.id.in_(selected),
                SkillVersion.status == "published",
                (Skill.workspace_id == self.context.workspace_id) | (Skill.workspace_id.is_(None)),
            )
            .order_by(Skill.slug, SkillVersion.version_no)
            .all()
        )
        packages: list[SkillPackage] = []
        for version, skill in rows:
            content = version.package_json.get("content", "")
            if not isinstance(content, str) or not content.strip():
                continue
            description = version.description.replace("\n", " ").strip()
            skill_md = (
                f"---\nname: {skill.slug}\ndescription: {description}\n---\n\n{content.strip()}\n"
            )
            raw_resources = version.package_json.get("resources", {})
            resources = raw_resources if isinstance(raw_resources, dict) else {}
            packages.append(SkillPackage(skill.slug, skill_md, resources))
        return tuple(packages)
