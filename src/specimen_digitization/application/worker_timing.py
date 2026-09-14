"""Additive authority for the single approved review run; no rolling clocks."""

from typing import Literal
from pydantic import Field, model_validator

from .domain import Record
from ..release_budget import APPROVAL_SHA256

TIMING_VERSION = "approved-worker-timing/v1"
USEFUL_SECONDS = 3485
CLEANUP_SECONDS = 3500
SAM_DISPATCH_REMAINING = 2135
PARENT_SECONDS = 600
FINALIZATION_SECONDS = 30


class ApprovedWorkerTiming(Record):
    version: Literal["approved-worker-timing/v1"]
    approval_sha256: str
    dispatch_started_at_unix: int = Field(gt=0, strict=True)
    sam_expires_at_unix: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def original_authority(self):
        if self.approval_sha256 != APPROVAL_SHA256:
            raise ValueError("Approved worker timing authority required")
        remaining = self.sam_expires_at_unix - self.dispatch_started_at_unix
        if not SAM_DISPATCH_REMAINING <= remaining <= 3600:
            raise ValueError("Original SAM dispatch lifetime is insufficient")
        return self

    @property
    def useful_until(self):
        return self.dispatch_started_at_unix + USEFUL_SECONDS

    @property
    def cleanup_until(self):
        return self.dispatch_started_at_unix + CLEANUP_SECONDS
