"""Inspect the actual pgvector column type without reading note data."""

from sqlalchemy import text


async def embedding_column_type(connection) -> str | None:
    return await connection.scalar(
        text(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = to_regclass('note_sections') "
            "AND attname = 'embedding' AND NOT attisdropped"
        )
    )
