"""
dedup_engine.py – Semantic de-duplication of test cases.

Before pushing a new test case to ADO we compare it against every
existing test case linked to the same User Story.  If the similarity
score meets or exceeds the configured threshold (default 90 %) the
engine recommends *updating* the existing work-item instead of
creating a duplicate.
"""

from __future__ import annotations

import difflib
import logging

from config import Settings
from models import ExistingTestCase, GeneratedTestCase

logger = logging.getLogger("test-sync-pro")


def _tc_signature(title: str, given: str, when: str, then: str) -> str:
    """Normalise a test case into a single comparable string."""
    return f"{title}\n{given}\n{when}\n{then}".strip().lower()


def _existing_signature(tc: ExistingTestCase) -> str:
    """Build a comparable signature from an existing ADO test case."""
    steps_text = "\n".join(
        f"{s.action} {s.expected_result}" for s in tc.steps
    )
    return f"{tc.title}\n{steps_text}".strip().lower()


def _similarity(a: str, b: str) -> float:
    """Return 0.0–1.0 similarity using SequenceMatcher (Ratcliff/Obershelp)."""
    return difflib.SequenceMatcher(None, a, b).ratio()


# ── Public API ──────────────────────────────────────────────────────────

class DedupResult:
    """Outcome of a single de-dup check."""

    __slots__ = ("is_duplicate", "matched_id", "score")

    def __init__(
        self,
        is_duplicate: bool = False,
        matched_id: int = 0,
        score: float = 0.0,
    ) -> None:
        self.is_duplicate = is_duplicate
        self.matched_id = matched_id
        self.score = score

    def __repr__(self) -> str:
        return (
            f"DedupResult(dup={self.is_duplicate}, "
            f"matched_id={self.matched_id}, score={self.score:.2f})"
        )


class DedupEngine:
    """Compare generated test cases against existing ones."""

    def __init__(
        self,
        existing: list[ExistingTestCase],
        threshold: float | None = None,
    ) -> None:
        self._threshold = threshold or Settings.DEDUP_THRESHOLD
        self._existing_sigs: list[tuple[int, str]] = [
            (tc.id, _existing_signature(tc)) for tc in existing
        ]
        logger.info(
            "Dedup engine loaded with %d existing TCs (threshold=%.0f%%)",
            len(existing),
            self._threshold * 100,
        )

    def check(self, tc: GeneratedTestCase) -> DedupResult:
        """Return whether *tc* is a semantic duplicate of an existing TC."""
        new_sig = _tc_signature(tc.title, tc.given, tc.when, tc.then)

        best_score = 0.0
        best_id = 0

        for existing_id, existing_sig in self._existing_sigs:
            score = _similarity(new_sig, existing_sig)
            if score > best_score:
                best_score = score
                best_id = existing_id

        if best_score >= self._threshold:
            logger.info(
                "Duplicate detected: '%s' ↔ existing #%s (%.1f%%)",
                tc.title,
                best_id,
                best_score * 100,
            )
            return DedupResult(
                is_duplicate=True, matched_id=best_id, score=best_score
            )

        return DedupResult(is_duplicate=False, matched_id=0, score=best_score)

    def check_batch(
        self, cases: list[GeneratedTestCase]
    ) -> list[tuple[GeneratedTestCase, DedupResult]]:
        """Check a list of generated TCs; return paired results."""
        return [(tc, self.check(tc)) for tc in cases]
