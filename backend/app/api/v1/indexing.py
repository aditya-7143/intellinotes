from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.api.v1.deps import get_current_user_id
from app.domain.models import Note, NoteIndexJob, NoteSection
from app.infrastructure.database.session import get_db
from app.infrastructure.embeddings.factory import get_embedding_provider
from app.infrastructure.rag.index import enqueue_note

router = APIRouter(prefix="/index", tags=["index"])


@router.get("/status")
async def index_status(
    db: Annotated[AsyncSession, Depends(get_db)], user_id=Depends(get_current_user_id)
):
    model = get_embedding_provider().model_key
    notes = await db.scalar(select(func.count()).select_from(Note).where(Note.user_id == user_id))
    indexed = await db.scalar(
        select(func.count(func.distinct(NoteSection.note_id))).where(
            NoteSection.user_id == user_id, NoteSection.embedding_model == model
        )
    )
    jobs = (
        await db.execute(
            select(NoteIndexJob.status, func.count())
            .where(NoteIndexJob.user_id == user_id)
            .group_by(NoteIndexJob.status)
        )
    ).all()
    return {"notes": notes, "indexed": indexed, "jobs": dict(jobs), "embedding_model": model}


@router.post("/reindex", status_code=202)
async def reindex(
    db: Annotated[AsyncSession, Depends(get_db)], user_id=Depends(get_current_user_id)
):
    notes = (
        await db.scalars(
            select(Note)
            .options(noload("*"))
            .where(Note.user_id == user_id)
            .order_by(Note.id)
            .with_for_update()
        )
    ).all()
    for note in notes:
        await enqueue_note(db, note)
    return {"queued": len(notes)}
