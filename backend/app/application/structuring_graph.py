"""Retrieve library context, draft/refine, and validate before human review."""

import difflib
import json
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph

from app.application.ports import FolderRepository, LLMProvider
from app.application.proposals import UpdateNoteOperation, apply_edits, parse_proposal
from app.application.retrieval import Section, SectionRetriever
from app.core.exceptions import ConflictError, ValidationError


class StructuringState(TypedDict, total=False):
    user_id: UUID
    snippet: str
    context: str | None
    feedback: str | None
    previous: dict | None
    sections: list[Section]
    library_context: str
    draft: dict
    result: dict


class StructuringWorkflow:
    def __init__(
        self,
        folders: FolderRepository,
        llm: LLMProvider,
        retriever: SectionRetriever,
    ):
        self.folders, self.llm = folders, llm
        self.retriever = retriever
        graph = StateGraph(StructuringState)
        graph.add_node("retrieve", self.retrieve)
        graph.add_node("draft", self.draft)
        graph.add_node("validate", self.validate)
        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "draft")
        graph.add_edge("draft", "validate")
        graph.add_edge("validate", END)
        self.graph = graph.compile()

    async def retrieve(self, state: StructuringState) -> dict:
        user_id = state["user_id"]
        # Filter again at this boundary so even an adapter error cannot leak another library.
        folder_paths = await self.folders.get_paths(user_id)
        query = "\n".join(
            filter(None, [state["snippet"], state.get("context"), state.get("feedback")])
        )
        sections = [
            section
            for section in await self.retriever.retrieve(user_id, query)
            if section.note.user_id == user_id
        ]
        context = {
            "instructions": state.get("context"),
            "feedback": state.get("feedback"),
            "previous_proposal": state.get("previous"),
            "existing_folder_paths": folder_paths[:200],
            "retrieved_sections": [
                {
                    "note_id": str(section.note.id),
                    "base_version": section.note.version,
                    "title": section.note.title,
                    "folder_path": section.note.folder_path,
                    "heading": section.heading,
                    "content": section.content,
                }
                for section in sections
            ],
        }
        return {"sections": sections, "library_context": json.dumps(context)}

    async def draft(self, state: StructuringState) -> dict:
        return {"draft": await self.llm.structure_notes(state["snippet"], state["library_context"])}

    def validate(self, state: StructuringState) -> dict:
        proposal = parse_proposal(state["draft"])
        sources = {section.note.id: section.note for section in state["sections"]}
        previews = []
        for operation in proposal.operations:
            if not isinstance(operation, UpdateNoteOperation):
                continue
            note = sources.get(operation.note_id)
            if note is None:
                raise ValidationError("AI selected a note outside the retrieved context")
            if operation.base_version != note.version:
                raise ConflictError("AI returned a stale note version; regenerate the proposal")
            after = apply_edits(note.content, operation.edits)
            previews.append(
                {
                    "note_id": str(note.id),
                    "title": note.title,
                    "folder_path": note.folder_path,
                    "before": note.content,
                    "after": after,
                    "diff": "".join(
                        difflib.unified_diff(
                            note.content.splitlines(keepends=True),
                            after.splitlines(keepends=True),
                            fromfile="Before",
                            tofile="After",
                        )
                    ),
                }
            )
        return {"result": {**proposal.model_dump(mode="json"), "_review": {"updates": previews}}}

    async def execute(
        self,
        user_id: UUID,
        snippet: str,
        context: str | None = None,
        previous: dict | None = None,
        feedback: str | None = None,
    ) -> dict:
        if not snippet.strip():
            raise ValidationError("Snippet cannot be empty")
        result = await self.graph.ainvoke(
            {
                "user_id": user_id,
                "snippet": snippet,
                "context": context,
                "previous": previous,
                "feedback": feedback,
            }
        )
        return result["result"]
