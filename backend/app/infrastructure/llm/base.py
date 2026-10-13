from abc import ABC, abstractmethod
from typing import Optional


class BaseLLMProvider(ABC):
    @abstractmethod
    async def structure_notes(self, snippet: str, context: Optional[str] = None) -> dict:
        pass

    @abstractmethod
    async def refine_structure(self, current_structure: dict, feedback: str) -> dict:
        pass


STRUCTURE_SYSTEM_PROMPT = """You are an expert at organizing information into structured notes. Given a text snippet, create a logical folder structure and notes.

Output a JSON object with this exact structure:
{
  "folders": [
    {"name": "folder_name", "path": "/full/path/to/folder"}
  ],
  "notes": [
    {
      "title": "note_title",
      "content": "note content in markdown",
      "folder_path": "/full/path/to/folder",
      "tags": ["tag1", "tag2"]
    }
  ]
}

Rules:
- Paths must start with "/" and use forward slashes
- Folder paths in notes must match a folder's path or be "/"
- Create logical groupings based on content
- Use descriptive, concise titles
- Content should be well-formatted markdown
- Tags should be relevant keywords
- Keep structure shallow (max 3 levels deep)
- Don't create empty folders
"""


REFINE_SYSTEM_PROMPT = """You are refining a previously generated note structure based on user feedback.

Current structure:
{current_structure}

User feedback: {feedback}

Return the refined structure in the same JSON format. Apply the feedback while maintaining logical organization."""
