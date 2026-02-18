"""
delta_analyzer.py – Identify what changed between the current Acceptance
Criteria and the test steps already recorded in ADO.

When existing test cases already cover parts of the story, the agent
should only generate tests for the *new / modified* requirements.
"""

from __future__ import annotations

import difflib
import logging

from models import ExistingTestCase, UserStory

logger = logging.getLogger("test-sync-pro")


def _extract_criteria_lines(ac_text: str) -> list[str]:
    """Split Acceptance Criteria into discrete, non-empty lines."""
    lines: list[str] = []
    for raw in ac_text.replace("\r\n", "\n").split("\n"):
        clean = raw.strip().lstrip("-•*0123456789.) ")
        if clean:
            lines.append(clean)
    return lines


def _existing_coverage_text(existing: list[ExistingTestCase]) -> str:
    """Flatten existing test titles + steps into one block for comparison."""
    parts: list[str] = []
    for tc in existing:
        parts.append(tc.title)
        for step in tc.steps:
            parts.append(step.action)
            parts.append(step.expected_result)
    return "\n".join(parts).lower()


def _line_is_covered(line: str, coverage_text: str, threshold: float = 0.70) -> bool:
    """Heuristic: is *line* already represented in the coverage text?"""
    if line.lower() in coverage_text:
        return True
    best = difflib.SequenceMatcher(
        None, line.lower(), coverage_text
    ).find_longest_match(0, len(line.lower()), 0, len(coverage_text))
    ratio = (best.size * 2) / (len(line) + len(coverage_text)) if coverage_text else 0
    return ratio >= threshold


# ── Public API ──────────────────────────────────────────────────────────

class DeltaAnalyzer:
    """Determines the *delta* between current AC and existing test coverage."""

    def __init__(
        self,
        story: UserStory,
        existing: list[ExistingTestCase],
    ) -> None:
        self._story = story
        self._existing = existing

    def compute_delta(self) -> str:
        """Return a human-readable description of uncovered AC lines.

        This text is injected into the LLM prompt so it only generates
        tests for the gap, avoiding unnecessary duplication.

        Returns an empty string if everything is already covered.
        """
        ac_lines = _extract_criteria_lines(self._story.acceptance_criteria)
        if not ac_lines:
            logger.warning("No Acceptance Criteria found on Story #%s.", self._story.id)
            return ""

        if not self._existing:
            logger.info("No existing test cases — full generation needed.")
            return ""

        coverage = _existing_coverage_text(self._existing)
        uncovered: list[str] = []

        for line in ac_lines:
            if not _line_is_covered(line, coverage):
                uncovered.append(line)
                logger.debug("Uncovered AC line: %s", line)
            else:
                logger.debug("Already covered AC line: %s", line)

        if not uncovered:
            logger.info("All Acceptance Criteria already covered by %d existing TCs.",
                        len(self._existing))
            return ""

        logger.info(
            "Delta found: %d of %d AC lines uncovered.",
            len(uncovered),
            len(ac_lines),
        )
        return "\n".join(f"- {line}" for line in uncovered)

    @property
    def has_existing_tests(self) -> bool:
        return bool(self._existing)
