from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.v1.deps import (
    get_current_user_id,
    get_folder_repo,
    get_llm,
    get_note_repo,
    get_proposal_repo,
    get_storage_repo,
)
from app.application.dtos import ProposalAction, StructureRequest, StructuringProposalResponse
from app.application.use_cases.structuring import (
    AcceptProposalUseCase,
    CreateStructuringProposalUseCase,
    FeedbackProposalUseCase,
    GetProposalUseCase,
    ListProposalsUseCase,
    RejectProposalUseCase,
)

router = APIRouter(prefix="/structuring", tags=["structuring"])


@router.post("", response_model=StructuringProposalResponse, status_code=status.HTTP_201_CREATED)
async def create_structuring_proposal(
    request: StructureRequest,
    user_id=Depends(get_current_user_id),
    proposal_repo=Depends(get_proposal_repo),
    llm=Depends(get_llm),
):
    use_case = CreateStructuringProposalUseCase(proposal_repo, llm)
    proposal = await use_case.execute(user_id, request.snippet, request.context)
    return proposal


@router.get("", response_model=list[StructuringProposalResponse])
async def list_proposals(
    status: str | None = None,
    user_id=Depends(get_current_user_id),
    proposal_repo=Depends(get_proposal_repo),
):
    from app.domain.models import ProposalStatus

    status_enum = None
    if status and status in [s.value for s in ProposalStatus]:
        status_enum = ProposalStatus(status)
    use_case = ListProposalsUseCase(proposal_repo)
    proposals = await use_case.execute(user_id, status_enum)
    return proposals


@router.get("/{proposal_id}", response_model=StructuringProposalResponse)
async def get_proposal(
    proposal_id: UUID,
    user_id=Depends(get_current_user_id),
    proposal_repo=Depends(get_proposal_repo),
):
    use_case = GetProposalUseCase(proposal_repo)
    proposal = await use_case.execute(proposal_id, user_id)
    return proposal


@router.post("/{proposal_id}/accept", response_model=dict)
async def accept_proposal(
    proposal_id: UUID,
    user_id=Depends(get_current_user_id),
    proposal_repo=Depends(get_proposal_repo),
    folder_repo=Depends(get_folder_repo),
    note_repo=Depends(get_note_repo),
    storage_repo=Depends(get_storage_repo),
    llm=Depends(get_llm),
):
    use_case = AcceptProposalUseCase(proposal_repo, folder_repo, note_repo, storage_repo, llm)
    result = await use_case.execute(proposal_id, user_id)
    return result


@router.post("/{proposal_id}/reject", response_model=StructuringProposalResponse)
async def reject_proposal(
    proposal_id: UUID,
    user_id=Depends(get_current_user_id),
    proposal_repo=Depends(get_proposal_repo),
):
    use_case = RejectProposalUseCase(proposal_repo)
    proposal = await use_case.execute(proposal_id, user_id)
    return proposal


@router.post("/{proposal_id}/feedback", response_model=StructuringProposalResponse)
async def feedback_proposal(
    proposal_id: UUID,
    action: ProposalAction,
    user_id=Depends(get_current_user_id),
    proposal_repo=Depends(get_proposal_repo),
    llm=Depends(get_llm),
):
    if action.action != "feedback":
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action")
    use_case = FeedbackProposalUseCase(proposal_repo, llm)
    proposal = await use_case.execute(proposal_id, user_id, action.feedback or "")
    return proposal
