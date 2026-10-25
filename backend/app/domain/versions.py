import hashlib
import json


def note_version(note) -> str:
    """Fingerprint all editable fields, including their database update timestamp."""
    snapshot = {
        "title": note.title,
        "content": note.content,
        "folder_path": note.folder_path,
        "tags": note.tags,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
