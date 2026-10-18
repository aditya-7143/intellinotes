import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.application.dtos import AcceptedFolderResponse, AcceptProposalResponse, NoteResponse
from app.application.ports import (
    AcceptanceTransaction,
    FolderRepository,
    LLMProvider,
    NoteRepository,
    ProposalRepository,
    StorageRepository,
)
from app.application.proposals import (
    CreateNoteOperation,
    UpdateNoteOperation,
    apply_edits,
    parse_proposal,
)
from app.application.structuring_graph import StructuringWorkflow
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import log_operation
from app.core.paths import validate_folder_path, validate_note_title, validate_relative_path
from app.domain.models import Folder, Note, ProposalStatus, StructuringProposal

logger = logging.getLogger("intellinotes.structuring")


@dataclass
class CreateStructuringProposalUseCase:
    proposal_repo: ProposalRepository
    llm_provider: LLMProvider
    note_repo: NoteRepository
    folder_repo: FolderRepository

    @log_operation("proposal.create")
    async def execute(
        self, user_id: UUID, snippet: str, context: Optional[str] = None
    ) -> StructuringProposal:
        if not snippet.strip():
            raise ValidationError("Snippet cannot be empty")

        proposed_structure = await StructuringWorkflow(
            self.note_repo, self.folder_repo, self.llm_provider
        ).execute(user_id, snippet, context)
        proposed_structure["_request_context"] = context
        parse_proposal(proposed_structure)

        proposal = StructuringProposal(
            user_id=user_id,
            input_snippet=snippet,
            proposed_structure=proposed_structure,
            status=ProposalStatus.PENDING,
        )
        created = await self.proposal_repo.create(proposal)
        logger.debug("Proposal staged proposal_id=%s user_id=%s", created.id, user_id)
        return created


@dataclass
class GetProposalUseCase:
    proposal_repo: ProposalRepository

    @log_operation("proposal.get")
    async def execute(self, proposal_id: UUID, user_id: UUID) -> StructuringProposal:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if not proposal or proposal.user_id != user_id:
            raise NotFoundError("Proposal not found")
        return proposal


@dataclass
class ListProposalsUseCase:
    proposal_repo: ProposalRepository

    @log_operation("proposal.list")
    async def execute(
        self, user_id: UUID, status: Optional[ProposalStatus] = None
    ) -> list[StructuringProposal]:
        return await self.proposal_repo.get_by_user(user_id, status)


@dataclass
class AcceptProposalUseCase:
    proposal_repo: ProposalRepository
    folder_repo: FolderRepository
    note_repo: NoteRepository
    storage_repo: StorageRepository
    transaction: AcceptanceTransaction

    @log_operation("proposal.accept")
    async def execute(self, proposal_id: UUID, user_id: UUID) -> AcceptProposalResponse:
        try:
            await self.transaction.lock_user(user_id)
            proposal = await self.proposal_repo.get_by_id(proposal_id, for_update=True)
            if not proposal or proposal.user_id != user_id:
                raise NotFoundError("Proposal not found")
            if proposal.status == ProposalStatus.ACCEPTED:
                receipt = proposal.proposed_structure.get("_acceptance")
                if receipt:
                    return AcceptProposalResponse.model_validate(receipt)
                raise ConflictError("Proposal was already accepted")
            if proposal.status != ProposalStatus.PENDING:
                raise ConflictError("Proposal already processed")

            structure = parse_proposal(proposal.proposed_structure)
            created_folders: dict[str, Folder] = {}
            targets: dict[UUID, Note] = {}
            replacements: dict[UUID, str] = {}
            # Lock update targets in a stable order to avoid deadlocks.
            updates = sorted(
                (op for op in structure.operations if isinstance(op, UpdateNoteOperation)),
                key=lambda op: str(op.note_id),
            )
            for operation in updates:
                note = await self.note_repo.get_by_id(operation.note_id, for_update=True)
                if not note or note.user_id != user_id:
                    raise NotFoundError("Target note not found")
                if note.version != operation.base_version:
                    raise ConflictError("Target note changed; regenerate the proposal")
                validate_note_title(note.title)
                validate_folder_path(note.folder_path)
                key = note.storage_key or self._storage_key(user_id, note.folder_path, note.title)
                validate_relative_path(key)
                if not key.startswith(f"{user_id}/"):
                    raise ValidationError("Target file is outside the user's library")
                if await self.storage_repo.get(key) != note.content.encode():
                    raise ConflictError(
                        "Target file differs from the note; reconcile it before updating"
                    )
                targets[note.id] = note
                replacements[note.id] = apply_edits(note.content, operation.edits)

            # Reject every collision before changing folders, files, or notes.
            for operation in structure.operations:
                if isinstance(operation, CreateNoteOperation):
                    key = self._storage_key(user_id, operation.folder_path, operation.title)
                    if await self.note_repo.get_by_storage_key(
                        key
                    ) or await self.storage_repo.exists(key):
                        raise ConflictError("A note already exists at a proposed destination")

            for folder in structure.folders:
                await self._ensure_folder(user_id, folder.path, created_folders)

            saved_notes = []
            for operation in structure.operations:
                if isinstance(operation, CreateNoteOperation):
                    folder = await self._ensure_folder(
                        user_id, operation.folder_path, created_folders
                    )
                    key = self._storage_key(user_id, operation.folder_path, operation.title)
                    await self.transaction.save(key, operation.content.encode(), expected=None)
                    note = Note(
                        user_id=user_id,
                        folder_id=folder.id if folder else None,
                        title=operation.title,
                        content=operation.content,
                        folder_path=operation.folder_path,
                        tags=operation.tags,
                        storage_key=key,
                    )
                    note = await self.note_repo.create(note)
                else:
                    note = targets[operation.note_id]
                    key = note.storage_key or self._storage_key(
                        user_id, note.folder_path, note.title
                    )
                    await self.transaction.save(
                        key, replacements[note.id].encode(), expected=note.content.encode()
                    )
                    note.content = replacements[note.id]
                    note.storage_key = key
                    note = await self.note_repo.update(note)
                saved_notes.append(NoteResponse.model_validate(note))
                logger.debug("Note staged proposal_id=%s note_id=%s", proposal_id, note.id)

            response = AcceptProposalResponse(
                folders=[
                    AcceptedFolderResponse.model_validate(folder)
                    for folder in created_folders.values()
                ],
                notes=saved_notes,
            )
            # Cache the exact response for retrying a successful acceptance.
            proposal.proposed_structure = {
                **proposal.proposed_structure,
                "_acceptance": response.model_dump(mode="json"),
            }
            proposal.status = ProposalStatus.ACCEPTED
            await self.proposal_repo.update(proposal)
            await self.transaction.commit()
            logger.debug(
                "Proposal committed proposal_id=%s notes=%d", proposal_id, len(saved_notes)
            )
            return response
        except BaseException:
            await self.transaction.rollback()
            raise

    @staticmethod
    def _storage_key(user_id: UUID, folder_path: str, title: str) -> str:
        key = f"{user_id}/{folder_path.strip('/')}/{title}.md".replace("//", "/")
        validate_relative_path(key)
        if len(key) > 1000:
            raise ValidationError("Note storage path is too long")
        return key

    async def _ensure_folder(
        self, user_id: UUID, path: str, folders: dict[str, Folder]
    ) -> Optional[Folder]:
        if path == "/":
            return None
        if path in folders:
            return folders[path]
        parent = await self._ensure_folder(user_id, path.rsplit("/", 1)[0] or "/", folders)
        folder = await self.folder_repo.get_by_path(user_id, path)
        if folder:
            if folder.parent_id != (parent.id if parent else None):
                raise ConflictError(
                    "Existing folder hierarchy is inconsistent; repair it before saving"
                )
        else:
            folder = await self.folder_repo.create(
                Folder(
                    user_id=user_id,
                    name=path.rsplit("/", 1)[-1],
                    parent_id=parent.id if parent else None,
                    path=path,
                )
            )
        folders[path] = folder
        return folder


@dataclass
class RejectProposalUseCase:
    proposal_repo: ProposalRepository

    @log_operation("proposal.reject")
    async def execute(self, proposal_id: UUID, user_id: UUID) -> StructuringProposal:
        proposal = await self.proposal_repo.get_by_id(proposal_id, for_update=True)
        if not proposal or proposal.user_id != user_id:
            raise NotFoundError("Proposal not found")

        if proposal.status != ProposalStatus.PENDING:
            raise ValidationError("Proposal already processed")

        proposal.status = ProposalStatus.REJECTED
        return await self.proposal_repo.update(proposal)


@dataclass
class FeedbackProposalUseCase:
    proposal_repo: ProposalRepository
    llm_provider: LLMProvider
    note_repo: NoteRepository
    folder_repo: FolderRepository

    @log_operation("proposal.feedback")
    async def execute(self, proposal_id: UUID, user_id: UUID, feedback: str) -> StructuringProposal:
        proposal = await self.proposal_repo.get_by_id(proposal_id, for_update=True)
        if not proposal or proposal.user_id != user_id:
            raise NotFoundError("Proposal not found")

        if proposal.status != ProposalStatus.PENDING:
            raise ValidationError("Proposal already processed")

        if not feedback.strip():
            raise ValidationError("Feedback cannot be empty")
        context = proposal.proposed_structure.get("_request_context")
        previous = parse_proposal(proposal.proposed_structure).model_dump(mode="json")
        refined = await StructuringWorkflow(
            self.note_repo, self.folder_repo, self.llm_provider
        ).execute(user_id, proposal.input_snippet, context, previous, feedback)
        refined["_request_context"] = context
        parse_proposal(refined)
        proposal.proposed_structure = refined
        proposal.feedback = feedback
        return await self.proposal_repo.update(proposal)
