"""Load authoritative Markdown through the storage port."""

from app.application.ports import StorageRepository
from app.core.exceptions import ConflictError, ValidationError
from app.core.logging import log_operation
from app.core.paths import validate_relative_path
from app.domain.models import Note


@log_operation("application.note_content.load_note_content")
async def load_note_content(note: Note, storage: StorageRepository) -> Note:
    key = note.storage_key
    if not key:
        raise ConflictError("Note has no file reference; reconcile the library")
    validate_relative_path(key)
    if not key.startswith(f"{note.user_id}/"):
        raise ValidationError("Note file is outside the user's library")
    data = await storage.get(key)
    if data is None:
        raise ConflictError("Note file is missing; restore it or remove its library entry")
    try:
        note.content = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError("Note file must contain UTF-8 text") from error
    return note
