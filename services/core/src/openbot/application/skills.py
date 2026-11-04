"""Read-only skill instruction loader with provenance and draft-only generation (OB-066)."""

import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import jsonschema

_ALLOWED_SKILL_CAPABILITIES = frozenset(
    {
        "workspace.list",
        "workspace.read",
        "workspace.search",
        "workspace.propose_patch",
        "browser.open",
        "browser.extract",
    }
)


@dataclass(frozen=True, slots=True)
class SkillManifestSpec:
    skill_id: str
    name: str
    version: str
    source_uri: str
    license: str
    sha256: str
    required_capabilities: tuple[str, ...]
    instructions_markdown: str


@dataclass(frozen=True, slots=True)
class LoadedReadOnlySkill:
    skill_id: str
    name: str
    version: str
    source_uri: str
    license: str
    sha256: str
    required_capabilities: tuple[str, ...]
    instructions_markdown: str
    provenance_kind: Literal["READONLY_SKILL_INSTRUCTION"] = "READONLY_SKILL_INSTRUCTION"
    can_mutate_policy: Literal[False] = False
    can_expand_workspace: Literal[False] = False
    can_promote_reference_only_components: Literal[False] = False


@dataclass(frozen=True, slots=True)
class GeneratedSkillDraft:
    draft_id: str
    name: str
    instructions_markdown: str
    status: Literal["DRAFT_NOT_INSTALLED"] = "DRAFT_NOT_INSTALLED"
    auto_installed: Literal[False] = False


class ReadOnlySkillLoader:
    """Load skills strictly as read-only instructions; never grant policy or workspace mutation."""

    def __init__(self, *, schema_path: Path) -> None:
        self._schema = json.loads(schema_path.read_text(encoding="utf-8"))

    def load_readonly_skill(self, spec: SkillManifestSpec) -> LoadedReadOnlySkill:
        doc = {
            "schema_version": "1.1",
            "skill_id": spec.skill_id,
            "name": spec.name,
            "version": spec.version,
            "source_uri": spec.source_uri,
            "license": spec.license,
            "sha256": spec.sha256,
            "required_capabilities": list(spec.required_capabilities),
        }
        jsonschema.validate(instance=doc, schema=self._schema)
        for cap in spec.required_capabilities:
            if cap not in _ALLOWED_SKILL_CAPABILITIES:
                raise PermissionError(f"FORBIDDEN_SKILL_CAPABILITY: {cap}")

        return LoadedReadOnlySkill(
            skill_id=spec.skill_id,
            name=spec.name,
            version=spec.version,
            source_uri=spec.source_uri,
            license=spec.license,
            sha256=spec.sha256,
            required_capabilities=spec.required_capabilities,
            instructions_markdown=spec.instructions_markdown,
        )

    def create_generated_skill_draft(
        self, *, name: str, instructions_markdown: str
    ) -> GeneratedSkillDraft:
        return GeneratedSkillDraft(
            draft_id="skd_" + secrets.token_hex(10),
            name=name,
            instructions_markdown=instructions_markdown,
        )
