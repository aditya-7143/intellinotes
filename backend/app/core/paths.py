"""Validation shared by proposals and storage adapters."""

from app.core.exceptions import ValidationError


def validate_relative_path(value: str) -> str:
    if not value or value.startswith("/") or "\\" in value:
        raise ValidationError("Invalid storage path")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValidationError("Control characters are not allowed in paths")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise ValidationError("Paths must not contain empty or traversal segments")
    return value


def validate_folder_path(value: str) -> str:
    if value == "/":
        return value
    if not value.startswith("/") or len(value) > 900:
        raise ValidationError("Folder paths must be absolute and at most 900 characters")
    validate_relative_path(value[1:])
    if any(len(part.encode("utf-8")) > 240 for part in value[1:].split("/")):
        raise ValidationError("Folder names are too long")
    return value


def validate_note_title(value: str) -> str:
    if not value.strip() or value != value.strip() or "/" in value or "\\" in value:
        raise ValidationError("Note titles must be nonempty filenames without separators")
    validate_relative_path(value)
    if len(value.encode("utf-8")) > 240:
        raise ValidationError("Note title is too long for storage")
    return value
