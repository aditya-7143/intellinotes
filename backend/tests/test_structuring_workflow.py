import json
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock
from uuid import uuid4

from app.application.retrieval import chunk_sections, split_sections, split_text
from app.application.structuring_graph import StructuringWorkflow
from app.application.use_cases.structuring import (
    CreateStructuringProposalUseCase,
    FeedbackProposalUseCase,
)
from app.core.exceptions import ConflictError, ValidationError
from app.domain.models import Note, ProposalStatus, StructuringProposal


def make_note(
    user_id, content="# Authentication\nJWT tokens\n\n## Refresh\nRotate refresh tokens.\n"
):
    return Note(
        id=uuid4(),
        user_id=user_id,
        title="Authentication",
        folder_path="/Backend",
        content=content,
        tags=["jwt"],
    )


class RetrievalTests(TestCase):
    def test_library_splitter_preserves_whitespace_and_unicode(self):
        for content in ["  first\n\n  second 🌍\n\n  ", "🌍" * 1000, " " * 2400]:
            with self.subTest(length=len(content)):
                chunks = split_text(content)
                self.assertEqual("".join(chunks), content)
                self.assertTrue(all(len(chunk.encode()) <= 1200 for chunk in chunks))

    def test_chunks_preserve_exact_content_and_bound_utf8_inputs(self):
        note = make_note(uuid4(), "# Guide\n" + "Some text 🌍\n" * 300)
        chunks = chunk_sections(note)
        self.assertEqual("".join(chunk.content for chunk in chunks), note.content)
        self.assertTrue(all(len(chunk.content.encode()) <= 1200 for chunk in chunks))
        self.assertEqual(split_text(""), [])

    def test_fenced_headings_are_not_sections(self):
        note = make_note(uuid4(), "# Guide\n```python\n# comment\n```\n## Next\nText")
        self.assertEqual([section.heading for section in split_sections(note)], ["Guide", "Next"])


class WorkflowTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = uuid4()
        self.note = make_note(self.user)
        self.notes, self.folders, self.llm = AsyncMock(), AsyncMock(), AsyncMock()
        self.notes.get_by_user.return_value = [self.note]
        self.folders.get_paths.return_value = []
        self.retriever = AsyncMock()
        self.retriever.retrieve.return_value = [split_sections(self.note)[1]]
        self.workflow = StructuringWorkflow(self.folders, self.llm, self.retriever)
        self.llm.structure_notes.return_value = {
            "schema_version": 2,
            "folders": [],
            "operations": [
                {
                    "action": "update",
                    "note_id": str(self.note.id),
                    "base_version": self.note.version,
                    "reason": "Extend refresh guidance",
                    "edits": [
                        {
                            "action": "insert_after",
                            "anchor": "Rotate refresh tokens.",
                            "content": "\nInvalidate the previous token.",
                            "target_section": "Refresh",
                        }
                    ],
                }
            ],
        }

    async def test_graph_retrieves_and_previews_without_writing(self):
        result = await self.workflow.execute(self.user, "refresh tokens invalidate previous")
        preview = result["_review"]["updates"][0]
        self.assertEqual(preview["before"], self.note.content)
        self.assertIn("Invalidate the previous token.", preview["after"])
        self.assertIn("# Authentication\nJWT tokens", preview["after"])
        self.assertIn("+Invalidate", preview["diff"])
        self.retriever.retrieve.assert_awaited_once_with(
            self.user, "refresh tokens invalidate previous"
        )
        self.notes.get_by_user.assert_not_awaited()
        self.notes.update.assert_not_awaited()
        context = json.loads(self.llm.structure_notes.call_args.args[1])
        self.assertEqual(context["retrieved_sections"][0]["heading"], "Refresh")

    async def test_other_user_content_is_never_sent_to_llm(self):
        private = make_note(uuid4(), "# Secret\nrefresh tokens private")
        self.retriever.retrieve.return_value.extend(split_sections(private))
        await self.workflow.execute(self.user, "refresh tokens")
        self.assertNotIn("private", self.llm.structure_notes.call_args.args[1])

    async def test_unretrieved_update_rejected(self):
        self.llm.structure_notes.return_value["operations"][0]["note_id"] = str(uuid4())
        with self.assertRaises(ValidationError):
            await self.workflow.execute(self.user, "refresh")

    async def test_stale_version_rejected(self):
        self.llm.structure_notes.return_value["operations"][0]["base_version"] = "a" * 64
        with self.assertRaises(ConflictError):
            await self.workflow.execute(self.user, "refresh")

    async def test_missing_anchor_rejected(self):
        self.llm.structure_notes.return_value["operations"][0]["edits"][0]["anchor"] = "Missing"
        with self.assertRaises(ConflictError):
            await self.workflow.execute(self.user, "refresh")

    async def test_empty_library_allows_creation(self):
        self.retriever.retrieve.return_value = []
        self.llm.structure_notes.return_value = {
            "notes": [
                {
                    "title": "JWT",
                    "content": "JWT notes",
                    "folder_path": "/",
                    "tags": [],
                }
            ]
        }
        result = await self.workflow.execute(self.user, "JWT")
        self.assertEqual(result["operations"][0]["action"], "create")
        self.assertEqual(result["_review"]["updates"], [])

    async def test_invalid_result_does_not_create_proposal(self):
        self.llm.structure_notes.return_value = {"notes": []}
        repo = AsyncMock()
        use_case = CreateStructuringProposalUseCase(repo, self.llm, self.folders, self.retriever)
        with self.assertRaises(ValidationError):
            await use_case.execute(self.user, "refresh")
        repo.create.assert_not_awaited()

    async def test_feedback_retrieves_fresh_content_and_preserves_instructions(self):
        repo = AsyncMock()
        repo.update.side_effect = lambda proposal: proposal
        repo.get_by_id.return_value = StructuringProposal(
            id=uuid4(),
            user_id=self.user,
            status=ProposalStatus.PENDING,
            input_snippet="refresh tokens",
            proposed_structure={
                "notes": [{"title": "JWT", "content": "Original", "folder_path": "/"}],
                "_request_context": "Keep code unchanged",
            },
        )
        use_case = FeedbackProposalUseCase(repo, self.llm, self.folders, self.retriever)
        proposal = await use_case.execute(
            repo.get_by_id.return_value.id, self.user, "Use refresh section"
        )
        self.assertEqual(proposal.proposed_structure["_request_context"], "Keep code unchanged")
        context = json.loads(self.llm.structure_notes.call_args.args[1])
        self.assertEqual(context["feedback"], "Use refresh section")
        self.retriever.retrieve.assert_awaited_once_with(
            self.user, "refresh tokens\nKeep code unchanged\nUse refresh section"
        )
        self.assertEqual(context["instructions"], "Keep code unchanged")
        self.assertEqual(context["previous_proposal"]["schema_version"], 2)
