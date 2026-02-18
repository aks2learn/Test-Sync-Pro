"""
models.py – Plain data-classes shared across every module.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class UserStory:
    """Represents an Azure DevOps User Story work item."""

    id: int
    title: str
    description: str
    acceptance_criteria: str
    priority: int = 2
    tags: list[str] = field(default_factory=list)
    state: str = ""


@dataclass
class TestStep:
    """A single action + expected-result pair inside a test case."""

    action: str
    expected_result: str


@dataclass
class GeneratedTestCase:
    """A BDD test case produced by the AI generator."""

    title: str
    given: str
    when: str
    then: str
    steps: list[TestStep] = field(default_factory=list)
    priority: int = 2
    tags: list[str] = field(default_factory=list)
    category: str = "Regression"          # Smoke | Sanity | Regression
    test_type: str = "Positive"           # Positive | Negative | Edge


@dataclass
class ExistingTestCase:
    """A test case that already exists in ADO, linked to the story."""

    id: int
    title: str
    steps: list[TestStep] = field(default_factory=list)
    priority: int = 2
    tags: list[str] = field(default_factory=list)
    revision: int = 1


@dataclass
class SyncResult:
    """Summary returned after the full sync cycle."""

    story_id: int
    created_ids: list[int] = field(default_factory=list)
    updated_ids: list[int] = field(default_factory=list)
    skipped_count: int = 0
    folder_map: dict[str, int] = field(default_factory=dict)
