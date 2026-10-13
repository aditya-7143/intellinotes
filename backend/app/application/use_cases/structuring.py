import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.application.ports import (
    FolderRepository,
    LLMProvider,
    NoteRepository,
    ProposalRepository,
    StorageRepository,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import log_operation
from app.domain.models import Folder, Note, ProposalStatus, StructuringProposal


logger = logging.getLogger("intellinotes.structuring")


@dataclass
class CreateStructuringProposalUseCase:
    proposal_repo: ProposalRepository
    llm_provider: LLMProvider

    @log_operation("proposal.create")
    async def execute(
        self, user_id: UUID, snippet: str, context: Optional[str] = None
    ) -> StructuringProposal:
        if not snippet.strip():
            raise ValidationError("Snippet cannot be empty")

        proposed_structure = await self.llm_provider.structure_notes(snippet, context)

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
    llm_provider: LLMProvider

    @log_operation("proposal.accept")
    async def execute(self, proposal_id: UUID, user_id: UUID) -> dict:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if not proposal or proposal.user_id != user_id:
            raise NotFoundError("Proposal not found")

        if proposal.status != ProposalStatus.PENDING:
            raise ValidationError("Proposal already processed")

        structure = proposal.proposed_structure
        created_folders: dict[str, Folder] = {}
        created_notes: list[Note] = []

        for folder_data in structure.get("folders", []):
            folder = await self._create_folder_recursive(
                user_id, folder_data, created_folders, self.folder_repo
            )
            created_folders[folder_data["path"]] = folder

        for note_data in structure.get("notes", []):
            folder_path = note_data.get("folder_path", "/")
            note_folder: Optional[Folder] = created_folders.get(folder_path)
            if not note_folder and folder_path != "/":
                note_folder = await self.folder_repo.get_by_path(user_id, folder_path)
                if note_folder:
                    created_folders[folder_path] = note_folder

            folder_id = note_folder.id if note_folder else None

            note = Note(
                user_id=user_id,
                folder_id=folder_id,
                title=note_data["title"],
                content=note_data["content"],
                folder_path=folder_path,
                tags=note_data.get("tags", []),
            )

            storage_key = f"{user_id}{folder_path}/{note_data['title']}.md".replace("//", "/")
            await self.storage_repo.save(storage_key, note_data["content"].encode())
            note.storage_key = storage_key

            created = await self.note_repo.create(note)
            created_notes.append(created)
            logger.debug("Note staged proposal_id=%s note_id=%s folder_id=%s", proposal_id, created.id, folder_id)

        logger.debug("Acceptance staged proposal_id=%s folders=%d notes=%d", proposal_id, len(created_folders), len(created_notes))
        proposal.status = ProposalStatus.ACCEPTED
        await self.proposal_repo.update(proposal)

        return {
            "folders": list(created_folders.values()),
            "notes": created_notes,
        }

    async def _create_folder_recursive(
        self,
        user_id: UUID,
        folder_data: dict,
        created_folders: dict[str, Folder],
        folder_repo: FolderRepository,
    ) -> Folder:
        path = folder_data["path"]
        if path in created_folders:
            return created_folders[path]

        existing = await folder_repo.get_by_path(user_id, path)
        if existing:
            created_folders[path] = existing
            return existing

        # Calculate parent path
        normalized = "/" + path.strip("/")
        parts = normalized.split("/")
        parent: Optional[Folder] = None
        if len(parts) > 2:
            parent_path = "/".join(parts[:-1])
            parent = created_folders.get(parent_path)
            if not parent:
                parent = await folder_repo.get_by_path(user_id, parent_path)

        folder = Folder(
            user_id=user_id,
            name=folder_data["name"],
            parent_id=parent.id if parent else None,
            path=path,
        )
        created = await folder_repo.create(folder)
        created_folders[path] = created
        logger.debug("Folder staged folder_id=%s parent_id=%s", created.id, created.parent_id)
        return created


@dataclass
class RejectProposalUseCase:
    proposal_repo: ProposalRepository

    @log_operation("proposal.reject")
    async def execute(self, proposal_id: UUID, user_id: UUID) -> StructuringProposal:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
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

    @log_operation("proposal.feedback")
    async def execute(self, proposal_id: UUID, user_id: UUID, feedback: str) -> StructuringProposal:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if not proposal or proposal.user_id != user_id:
            raise NotFoundError("Proposal not found")

        if proposal.status != ProposalStatus.PENDING:
            raise ValidationError("Proposal already processed")

        refined = await self.llm_provider.refine_structure(proposal.proposed_structure, feedback)
        proposal.proposed_structure = refined
        proposal.feedback = feedback
        return await self.proposal_repo.update(proposal)
