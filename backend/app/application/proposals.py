"""Versioned edit proposals; legacy folders/notes proposals remain readable."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic import ValidationError as SchemaError

from app.core.exceptions import ConflictError, ValidationError
from app.core.logging import log_operation
from app.core.paths import validate_folder_path, validate_note_title


class ProposedFolder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    path: str

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        return validate_folder_path(value)


class CreateNoteOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["create"] = "create"
    title: str
    content: str = Field(min_length=1)
    folder_path: str = "/"
    tags: list[str] = Field(default_factory=list)
    reason: str = Field(default="", max_length=2000)

    @field_validator("title")
    @classmethod
    def safe_title(cls, value: str) -> str:
        return validate_note_title(value)

    @field_validator("folder_path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        return validate_folder_path(value)

    @field_validator("content")
    @classmethod
    def nonblank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Note content cannot be blank")
        return value


class ProposedEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["replace", "insert_before", "insert_after"]
    anchor: str = Field(min_length=1)
    content: str
    target_section: str | None = None


class UpdateNoteOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["update"]
    note_id: UUID
    base_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    edits: list[ProposedEdit] = Field(min_length=1)
    reason: str = Field(default="", max_length=2000)


class EditProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[2] = 2
    folders: list[ProposedFolder] = Field(default_factory=list)
    operations: list[
        Annotated[CreateNoteOperation | UpdateNoteOperation, Field(discriminator="action")]
    ] = Field(min_length=1)


@log_operation("application.proposals.EditProposal.parse_proposal")
def parse_proposal(structure: dict) -> EditProposal:
    if not isinstance(structure, dict):
        raise ValidationError("Proposal must be a JSON object")
    try:
        if "schema_version" not in structure:
            if not isinstance(structure.get("notes"), list):
                raise ValidationError("Proposal must contain a notes list")
            structure = {
                "schema_version": 2,
                "folders": structure.get("folders", []),
                "operations": [{**note, "action": "create"} for note in structure["notes"]],
            }
        else:
            structure = {
                key: value
                for key, value in structure.items()
                if key not in {"_acceptance", "_review", "_request_context"}
            }
        proposal = EditProposal.model_validate(structure)
    except (SchemaError, TypeError, ValueError) as error:
        raise ValidationError("AI proposal has an invalid structure") from error
    paths = set()
    for folder in proposal.folders:
        if folder.path == "/" or folder.name != folder.path.rsplit("/", 1)[-1]:
            raise ValidationError("Folder names must match their paths")
        if folder.path in paths:
            raise ValidationError("Proposal contains duplicate folders")
        paths.add(folder.path)
    destinations, targets = set(), set()
    for operation in proposal.operations:
        if isinstance(operation, CreateNoteOperation):
            destination = (operation.folder_path, operation.title)
            if destination in destinations:
                raise ValidationError("Proposal contains duplicate note destinations")
            destinations.add(destination)
        else:
            if operation.note_id in targets:
                raise ValidationError("Combine edits for a note into one operation")
            targets.add(operation.note_id)
    return proposal


@log_operation("application.proposals.EditProposal.apply_edits")
def apply_edits(content: str, edits: list[ProposedEdit]) -> str:
    """Each anchor is resolved against the original document, never a shifted line number."""
    spans = []
    for edit in edits:
        if content.count(edit.anchor) != 1:
            raise ConflictError("Edit anchor is missing or ambiguous; regenerate the proposal")
        start = content.index(edit.anchor)
        end = start + len(edit.anchor)
        if edit.action == "insert_before":
            end = start
        elif edit.action == "insert_after":
            start = end
        spans.append((start, end, edit.content))
    spans.sort(key=lambda span: (span[0], span[1]))
    for previous, current in zip(spans, spans[1:]):
        if current[0] < previous[1] or current[0] == previous[0]:
            raise ValidationError("Proposal contains overlapping edits")
    for start, end, replacement in reversed(spans):
        content = content[:start] + replacement + content[end:]
    if not content.strip():
        raise ValidationError("Edits cannot leave a note empty")
    return content
