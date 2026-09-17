"""Validated actions for the experimental single-task decision loop.

This module only validates decisions. It does not execute tools or mark tasks
complete; the future loop must enforce evidence, step and time constraints.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter


ActionText = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=512),
]


class _TaskAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")

    # A short observable explanation, not a request for private model reasoning.
    reason: ActionText


class SearchAction(_TaskAction):
    """Request one search with a bounded, non-empty query."""

    action: Literal["search"]
    query: ActionText


class FinishAction(_TaskAction):
    """Propose ending evidence collection; does not certify answer quality."""

    action: Literal["finish"]


TaskAction = Annotated[Union[SearchAction, FinishAction], Field(discriminator="action")]
_ACTION_ADAPTER = TypeAdapter(TaskAction)


def parse_task_action(payload: object) -> SearchAction | FinishAction:
    """Validate a decoded action payload, raising ValidationError on rejection.

    JSON strings and Markdown fences are deliberately not parsed or repaired.
    Query and reason limits count characters after stripping outer whitespace.
    """
    return _ACTION_ADAPTER.validate_python(payload)
