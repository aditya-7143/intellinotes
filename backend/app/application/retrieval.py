"""Heading-aware chunks for semantic retrieval; splitting happens during indexing."""

import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.domain.models import Note


@dataclass
class Section:
    note: Note
    heading: str
    content: str


def split_sections(note: Note) -> list[Section]:
    # Headings inside fenced code blocks are content, not section boundaries.
    sections, lines, heading, fence = [], [], "Introduction", None
    for line in note.content.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
        match = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", line) if fence is None else None
        if match:
            if lines:
                sections.append(Section(note, heading, "".join(lines)))
            heading, lines = match.group(1), []
        lines.append(line)
    if lines:
        sections.append(Section(note, heading, "".join(lines)))
    return sections


class SectionRetriever(Protocol):
    async def retrieve(self, user_id: UUID, query: str) -> list[Section]: ...


def split_text(text: str, max_bytes: int = 1200) -> list[str]:
    """Use LangChain to split at paragraph/line/word boundaries, preserving anchors."""
    if max_bytes < 4:
        raise ValueError("Chunk size must accommodate a UTF-8 character (at least 4 bytes)")
    return RecursiveCharacterTextSplitter(
        chunk_size=max_bytes,
        chunk_overlap=0,
        length_function=lambda value: len(value.encode("utf-8")),
        keep_separator=True,
        strip_whitespace=False,
    ).split_text(text)


def chunk_sections(note: Note) -> list[Section]:
    return [
        Section(note, section.heading, chunk)
        for section in split_sections(note)
        for chunk in split_text(section.content)
    ]


def embedding_text(section: Section) -> str:
    metadata = f"{section.note.title} | {section.note.folder_path} | {section.heading} | {' '.join(section.note.tags)}"
    # Bound metadata separately so very long tags cannot crowd out note content.
    metadata = metadata.encode("utf-8")[:500].decode("utf-8", errors="ignore")
    return metadata + "\n" + section.content
