"""Request-time section retrieval. No stale index or external embedding service."""

import math
import re
from collections import Counter
from dataclasses import dataclass

from app.domain.models import Note

STOP_WORDS = set(
    "a an the is are to of in on for and or with this that it be as at by from".split()
)


def tokens(text: str) -> list[str]:
    return [word for word in re.findall(r"[\w+#.-]+", text.lower()) if word not in STOP_WORDS]


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


def retrieve_sections(notes: list[Note], query: str, limit: int = 5) -> list[Section]:
    """BM25-style lexical ranking, weighted toward titles, paths, tags and headings."""
    sections = [section for note in notes for section in split_sections(note)]
    documents = [
        tokens(
            f"{section.note.title} {section.note.folder_path} {' '.join(section.note.tags)} "
            f"{section.heading} " * 3 + section.content
        )
        for section in sections
    ]
    if not documents:
        return []
    frequencies = Counter(word for document in documents for word in set(document))
    average = sum(map(len, documents)) / len(documents) or 1
    ranked = []
    for index, document in enumerate(documents):
        counts = Counter(document)
        score = 0.0
        for word in set(tokens(query)):
            count = counts[word]
            inverse = math.log(
                1 + (len(documents) - frequencies[word] + 0.5) / (frequencies[word] + 0.5)
            )
            score += inverse * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * len(document) / average))
        if score > 0:
            ranked.append((score, index))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    # Bound prompt size; only complete sections are used as exact edit anchors.
    return [sections[index] for _, index in ranked if len(sections[index].content) <= 12000][:limit]
