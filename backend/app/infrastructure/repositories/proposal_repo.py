from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.application.ports import ProposalRepository
from app.core.logging import log_operation
from app.domain.models import ProposalStatus, StructuringProposal


class SQLAlchemyProposalRepository(ProposalRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    @log_operation("infrastructure.repositories.proposal_repo.SQLAlchemyProposalRepository.create")
    async def create(self, proposal: StructuringProposal) -> StructuringProposal:
        self.session.add(proposal)
        await self.session.flush()
        await self.session.refresh(proposal)
        return proposal

    @log_operation(
        "infrastructure.repositories.proposal_repo.SQLAlchemyProposalRepository.get_by_id"
    )
    async def get_by_id(
        self, proposal_id: UUID, for_update: bool = False
    ) -> Optional[StructuringProposal]:
        query = (
            select(StructuringProposal)
            .options(noload("*"))
            .where(StructuringProposal.id == proposal_id)
        )
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    @log_operation(
        "infrastructure.repositories.proposal_repo.SQLAlchemyProposalRepository.get_by_user"
    )
    async def get_by_user(
        self, user_id: UUID, status: Optional[ProposalStatus] = None
    ) -> list[StructuringProposal]:
        query = (
            select(StructuringProposal)
            .options(noload("*"))
            .where(StructuringProposal.user_id == user_id)
        )
        if status:
            query = query.where(StructuringProposal.status == status)
        query = query.order_by(StructuringProposal.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    @log_operation("infrastructure.repositories.proposal_repo.SQLAlchemyProposalRepository.update")
    async def update(self, proposal: StructuringProposal) -> StructuringProposal:
        await self.session.flush()
        await self.session.refresh(proposal)
        return proposal

    @log_operation("infrastructure.repositories.proposal_repo.SQLAlchemyProposalRepository.delete")
    async def delete(self, proposal_id: UUID) -> bool:
        proposal = await self.get_by_id(proposal_id)
        if proposal:
            await self.session.delete(proposal)
            return True
        return False
