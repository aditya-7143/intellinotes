import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.deps import (
    get_current_user_id,
    get_folder_repo,
    get_note_repo,
    get_proposal_repo,
    get_storage_repo,
)
from app.api.v1.structuring import router
from app.application.proposals import ProposedEdit, apply_edits, parse_proposal
from app.application.use_cases.structuring import AcceptProposalUseCase
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.models import Note, ProposalStatus, StructuringProposal
from app.infrastructure.database.acceptance import SQLAlchemyAcceptanceTransaction
from app.infrastructure.database.session import get_db
from app.infrastructure.storage.local_storage import LocalStorage


class MemoryStorage:
    def __init__(self):
        self.files = {}
        self.writes = 0

    async def get(self, key):
        return self.files.get(key)

    async def save(self, key, content):
        self.writes += 1
        self.files[key] = content
        return key

    async def delete(self, key):
        return self.files.pop(key, None) is not None

    async def exists(self, key):
        return key in self.files


def populate(model):
    model.id = model.id or uuid4()
    model.created_at = model.created_at or datetime.now(timezone.utc)
    model.updated_at = datetime.now(timezone.utc)
    return model


class AcceptanceTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.user_id = uuid4()
        self.session = AsyncMock()
        self.storage = MemoryStorage()
        self.transaction = SQLAlchemyAcceptanceTransaction(self.session, self.storage)
        self.proposals, self.folders, self.notes = AsyncMock(), AsyncMock(), AsyncMock()
        self.folders.get_by_path.return_value = None
        self.folders.create.side_effect = lambda folder: folder
        self.notes.create.side_effect = populate
        self.notes.update.side_effect = populate
        self.notes.get_by_storage_key.return_value = None
        self.proposal = StructuringProposal(
            id=uuid4(),
            user_id=self.user_id,
            input_snippet="Original dump",
            status=ProposalStatus.PENDING,
            proposed_structure={
                "folders": [],
                "notes": [
                    {
                        "title": "GANs",
                        "content": "# GANs\nOriginal",
                        "tags": [],
                        "folder_path": "/AI/Models",
                    }
                ],
            },
        )
        self.proposals.get_by_id.return_value = self.proposal
        self.use_case = AcceptProposalUseCase(
            self.proposals,
            self.folders,
            self.notes,
            self.storage,
            self.transaction,
        )

    def prepare_update(self):
        self.note = populate(
            Note(
                user_id=self.user_id,
                title="GANs",
                content="# GANs\nOriginal",
                folder_path="/",
                tags=[],
                storage_key=f"{self.user_id}/GANs.md",
            )
        )
        self.notes.get_by_id.return_value = self.note
        self.storage.files[self.note.storage_key] = self.note.content.encode()
        self.proposal.proposed_structure = {
            "schema_version": 2,
            "folders": [],
            "operations": [
                {
                    "action": "update",
                    "note_id": str(self.note.id),
                    "base_version": self.note.version,
                    "edits": [
                        {
                            "action": "insert_after",
                            "anchor": "Original",
                            "content": "\nMore detail",
                            "target_section": "GANs",
                        }
                    ],
                }
            ],
        }

    async def test_legacy_creation_builds_parents_and_serializes(self):
        response = await self.use_case.execute(self.proposal.id, self.user_id)
        self.assertEqual([folder.path for folder in response.folders], ["/AI", "/AI/Models"])
        self.assertEqual(response.folders[1].parent_path, response.folders[0].path)
        self.assertEqual(response.notes[0].folder_path, response.folders[1].path)
        self.assertIn('"version":', response.model_dump_json())
        self.assertEqual(self.proposal.status, ProposalStatus.ACCEPTED)
        self.session.commit.assert_awaited_once()

    async def test_retry_returns_receipt_without_writing_again(self):
        first = await self.use_case.execute(self.proposal.id, self.user_id)
        second = await self.use_case.execute(self.proposal.id, self.user_id)
        self.assertEqual(first.model_dump(), second.model_dump())
        self.assertEqual(self.storage.writes, 1)
        self.notes.create.assert_awaited_once()

    async def test_legacy_accepted_proposal_cannot_write_again(self):
        self.proposal.status = ProposalStatus.ACCEPTED
        with self.assertRaises(ConflictError):
            await self.use_case.execute(self.proposal.id, self.user_id)
        self.assertEqual(self.storage.writes, 0)

    async def test_rejected_proposal_cannot_be_accepted(self):
        self.proposal.status = ProposalStatus.REJECTED
        with self.assertRaises(ConflictError):
            await self.use_case.execute(self.proposal.id, self.user_id)
        self.assertEqual(self.storage.writes, 0)

    async def test_other_users_proposal_rejected(self):
        self.proposal.user_id = uuid4()
        with self.assertRaises(NotFoundError):
            await self.use_case.execute(self.proposal.id, self.user_id)
        self.assertEqual(self.storage.writes, 0)

    async def test_collision_rejected_before_any_mutation(self):
        self.storage.files[f"{self.user_id}/AI/Models/GANs.md"] = b"Existing"
        with self.assertRaises(ConflictError):
            await self.use_case.execute(self.proposal.id, self.user_id)
        self.folders.create.assert_not_awaited()
        self.notes.create.assert_not_awaited()
        self.assertEqual(self.storage.writes, 0)

    async def test_database_collision_also_rejected(self):
        self.notes.get_by_storage_key.return_value = object()
        with self.assertRaises(ConflictError):
            await self.use_case.execute(self.proposal.id, self.user_id)
        self.assertEqual(self.storage.writes, 0)

    async def test_targeted_update_preserves_other_content(self):
        self.prepare_update()
        response = await self.use_case.execute(self.proposal.id, self.user_id)
        self.assertEqual(response.notes[0].content, "# GANs\nOriginal\nMore detail")
        self.notes.get_by_id.assert_awaited_once_with(self.note.id, for_update=True)
        self.notes.create.assert_not_awaited()

    async def test_stale_document_rejected(self):
        self.prepare_update()
        self.note.content = "Edited by user"
        with self.assertRaises(ConflictError):
            await self.use_case.execute(self.proposal.id, self.user_id)
        self.assertEqual(self.storage.writes, 0)

    async def test_other_users_target_rejected(self):
        self.prepare_update()
        self.note.user_id = uuid4()
        with self.assertRaises(NotFoundError):
            await self.use_case.execute(self.proposal.id, self.user_id)
        self.assertEqual(self.storage.writes, 0)

    async def test_external_file_change_rejected(self):
        self.prepare_update()
        self.storage.files[self.note.storage_key] = b"Edited outside app"
        with self.assertRaises(ConflictError):
            await self.use_case.execute(self.proposal.id, self.user_id)
        self.assertEqual(self.storage.writes, 0)

    async def test_commit_failure_restores_updated_file(self):
        self.prepare_update()
        self.session.commit.side_effect = RuntimeError("Database failure")
        with self.assertRaises(RuntimeError):
            await self.use_case.execute(self.proposal.id, self.user_id)
        self.assertEqual(self.storage.files[self.note.storage_key], b"# GANs\nOriginal")
        self.session.rollback.assert_awaited_once()

    async def test_commit_failure_removes_new_files(self):
        self.session.commit.side_effect = RuntimeError("Database failure")
        with self.assertRaises(RuntimeError):
            await self.use_case.execute(self.proposal.id, self.user_id)
        self.assertEqual(self.storage.files, {})

    async def test_later_write_failure_removes_earlier_files(self):
        self.proposal.proposed_structure["notes"].append(
            {
                "title": "VAEs",
                "content": "VAE notes",
                "folder_path": "/",
                "tags": [],
            }
        )
        self.notes.create.side_effect = [
            populate(
                Note(
                    user_id=self.user_id,
                    title="GANs",
                    content="# GANs\nOriginal",
                    folder_path="/AI/Models",
                    tags=[],
                )
            ),
            RuntimeError("Second insert failed"),
        ]
        with self.assertRaises(RuntimeError):
            await self.use_case.execute(self.proposal.id, self.user_id)
        self.assertEqual(self.storage.files, {})

    async def test_endpoint_returns_json_instead_of_serialization_500(self):
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[get_current_user_id] = lambda: self.user_id
        app.dependency_overrides[get_proposal_repo] = lambda: self.proposals
        app.dependency_overrides[get_folder_repo] = lambda: self.folders
        app.dependency_overrides[get_note_repo] = lambda: self.notes
        app.dependency_overrides[get_storage_repo] = lambda: self.storage
        app.dependency_overrides[get_db] = lambda: self.session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/api/v1/structuring/{self.proposal.id}/accept")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["notes"][0]["title"], "GANs")
        self.assertEqual(response.json()["folders"][1]["path"], "/AI/Models")


class ProposalValidationTests(TestCase):
    def test_invalid_proposals_rejected(self):
        for title, path in [
            ("../secret", "/"),
            ("Fine", "/../other"),
            ("Fine", "/AI//Models"),
            ("Fine", "/AI\\Models"),
        ]:
            with self.subTest(title=title, path=path), self.assertRaises(ValidationError):
                parse_proposal(
                    {"notes": [{"title": title, "content": "Text", "folder_path": path}]}
                )

    def test_duplicate_destinations_rejected(self):
        note = {"title": "Same", "content": "Text", "folder_path": "/"}
        with self.assertRaises(ValidationError):
            parse_proposal({"notes": [note, note]})

    def test_missing_fields_and_empty_notes_rejected(self):
        for structure in [None, [], {"notes": []}, {"notes": [{}]}, {"notes": "wrong"}]:
            with self.subTest(structure=structure), self.assertRaises(ValidationError):
                parse_proposal(structure)

    def test_ambiguous_anchor_rejected(self):
        with self.assertRaises(ConflictError):
            apply_edits(
                "Repeated Repeated",
                [ProposedEdit(action="replace", anchor="Repeated", content="New")],
            )

    def test_overlapping_edits_rejected(self):
        with self.assertRaises(ValidationError):
            apply_edits(
                "abcdef",
                [
                    ProposedEdit(action="replace", anchor="abcd", content="New"),
                    ProposedEdit(action="insert_after", anchor="ab", content="Inserted"),
                ],
            )

    def test_offsets_resolve_against_original_document(self):
        result = apply_edits(
            "Alpha\nBeta",
            [
                ProposedEdit(action="replace", anchor="Alpha", content="Much longer heading"),
                ProposedEdit(action="insert_after", anchor="Beta", content="\nGamma"),
            ],
        )
        self.assertEqual(result, "Much longer heading\nBeta\nGamma")

    def test_storage_rejects_traversal_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "notes"
            outside = Path(temporary) / "outside"
            outside.mkdir()
            storage = LocalStorage(str(base))
            (base / "escape").symlink_to(outside, target_is_directory=True)
            for key in ["../secret", "/absolute", "escape/secret", "a\\b", "a/../b"]:
                with self.subTest(key=key), self.assertRaises(ValidationError):
                    storage._get_full_path(key)
