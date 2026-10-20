"""Private bulk intake contracts. A saved photo is not a submitted specimen."""

from typing import Literal
from pydantic import Field
from .domain import Record

MAX_PHOTOS = 500
MAX_BYTES = 25_000_000
PRIVATE_KINDS = ('intake_draft', 'intake_item', 'intake_submission', 'intake_result', 'intake_connection', 'intake_oauth')
TERMINAL = frozenset({'sent', 'duplicate', 'held', 'cancelled'})


class Draft(Record):
    id: str
    owner_id: str
    collection_id: str
    name: str = 'Photo batch'
    state: Literal['draft', 'submitted', 'discarded'] = 'draft'
    entries: list[dict] = Field(default_factory=list)
    sensitive: bool = False
    revision: int = 0
    created_at: str
    submission_id: str | None = None
    remaining_draft_id: str | None = None
    submitted_entries: list[dict] = Field(default_factory=list, max_length=MAX_PHOTOS)
    submitted_at: str | None = None


class DraftInput(Record):
    client_id: str = Field(min_length=1, max_length=100)
    name: str = Field(default='Photo batch', min_length=1, max_length=200)


class SourceReference(Record):
    provider: Literal['files', 'camera', 'url', 'storage', 'google_drive', 'dropbox']
    connection_id: str | None = None
    object_id: str | None = Field(default=None, max_length=2048)
    version: str | None = Field(default=None, max_length=200)
    source_id: str | None = None
    url: str | None = Field(default=None, max_length=4096)


class DraftItemInput(Record):
    client_id: str = Field(min_length=1, max_length=100)
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(default='application/octet-stream', max_length=100)
    size_bytes: int | None = Field(default=None, gt=0, le=MAX_BYTES)
    sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    photo_sensitive: bool = Field(default=False, strict=True)
    source: SourceReference
    replaces_id: str | None = Field(default=None, max_length=100)


class DraftItem(Record):
    id: str
    client_id: str
    draft_id: str
    owner_id: str
    collection_id: str
    filename: str
    source: SourceReference
    media_type: str
    size_bytes: int | None = None
    sha256: str | None = None
    state: Literal['waiting', 'transferring', 'checking', 'ready', 'needs_attention'] = 'waiting'
    offset: int = 0
    chunks: list[dict] = Field(default_factory=list)
    asset: dict | None = None
    thumbnail_ref: str | None = None
    error: dict | None = None
    request_digest: str
    sensitive: bool = False
    policy_sensitive: bool = False
    derived_from: str | None = None
    revision: int = 0


class DraftEdit(Record):
    expected_revision: int = Field(ge=1)
    item_ids: list[str] = Field(min_length=1, max_length=MAX_PHOTOS)
    action: Literal['remove', 'restore', 'sensitive', 'include', 'exclude']
    value: bool | None = None


class SubmitInput(Record):
    expected_revision: int = Field(ge=1)
    item_ids: list[str] = Field(min_length=1, max_length=MAX_PHOTOS)


class Submission(Record):
    id: str
    draft_id: str
    owner_id: str
    collection_id: str
    entries: list[dict]
    total: int
    created_at: str
    sensitive: bool = False
    cancel_requested: bool = False
    revision: int = 0


class SubmissionItem(Record):
    id: str
    submission_id: str
    item_id: str
    owner_id: str
    collection_id: str
    state: Literal['waiting', 'transferring', 'checking', 'sent', 'duplicate', 'held', 'needs_attention', 'cancelled'] = 'waiting'
    specimen_id: str | None = None
    error: dict | None = None
    sensitive: bool = False
    revision: int = 0
    lease_token: str | None = None
    lease_until: float = 0


class ProviderConnection(Record):
    id: str
    owner_id: str
    collection_id: str
    provider: Literal['google_drive', 'dropbox']
    access: Literal['files', 'folders']
    state: Literal['connected', 'disconnected', 'needs_authorization', 'policy_blocked']
    account_label: str = ''
    account_id: str | None = None
    secret_ref: str | None = None
    sensitive: bool = False
    revision: int = 0
