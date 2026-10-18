from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class ProposalStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=72)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    settings: Optional[dict] = None


class UserResponse(UserBase):
    id: UUID
    created_at: datetime
    settings: dict

    class Config:
        from_attributes = True


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


class FolderBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: Optional[UUID] = None


class FolderCreate(FolderBase):
    pass


class FolderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    parent_id: Optional[UUID] = None


class FolderResponse(FolderBase):
    id: UUID
    user_id: UUID
    path: str
    created_at: datetime
    updated_at: datetime
    children: list["FolderResponse"] = []

    class Config:
        from_attributes = True


class NoteBase(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    folder_id: Optional[UUID] = None
    tags: list[str] = []


class NoteCreate(NoteBase):
    title: Optional[str] = Field(default=None, max_length=500)


class NoteUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    content: Optional[str] = Field(default=None, min_length=1)
    folder_id: Optional[UUID] = None
    tags: Optional[list[str]] = None


class NoteResponse(NoteBase):
    id: UUID
    user_id: UUID
    folder_path: str
    storage_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    version: str

    class Config:
        from_attributes = True


class AcceptedFolderResponse(BaseModel):
    """Acceptance returns flat folders, avoiding lazy relationship serialization."""

    id: UUID
    user_id: UUID
    name: str
    parent_id: Optional[UUID] = None
    path: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AcceptProposalResponse(BaseModel):
    folders: list[AcceptedFolderResponse]
    notes: list[NoteResponse]


class StructuringProposalBase(BaseModel):
    input_snippet: str = Field(min_length=1)
    proposed_structure: dict


class StructuringProposalCreate(StructuringProposalBase):
    pass


class StructuringProposalUpdate(BaseModel):
    feedback: Optional[str] = None


class StructuringProposalResponse(StructuringProposalBase):
    id: UUID
    user_id: UUID
    status: ProposalStatus
    feedback: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StructureRequest(BaseModel):
    snippet: str = Field(min_length=1)
    context: Optional[str] = None


class StructureProposal(BaseModel):
    folders: list[dict]
    notes: list[dict]


class ProposalAction(BaseModel):
    action: str = Field(pattern="^(accept|reject|feedback)$")
    feedback: Optional[str] = None


FolderResponse.model_rebuild()
