"""
folder_manager.py – Maps generated test cases into the correct ADO Test Suites.

Folder hierarchy under the Test Plan:
  ├─ Complete Test Cases   (every test case)
  ├─ Regression            (category == Regression)
  ├─ Smoke                 (category == Smoke)
  └─ Sanity                (category == Sanity)
"""

from __future__ import annotations

import logging

from ado_client import ADOClient
from models import GeneratedTestCase

logger = logging.getLogger("test-sync-pro")


class FolderManager:
    """Ensures the folder hierarchy exists and files tests into the right suites."""

    def __init__(self, ado: ADOClient) -> None:
        self._ado = ado
        self._folder_map: dict[str, int] = {}

    def setup_folders(self) -> dict[str, int]:
        """Create / verify the four required folders and cache their IDs."""
        self._folder_map = self._ado.ensure_folders()
        logger.info("Folder map: %s", self._folder_map)
        return self._folder_map

    def assign_test(
        self, test_case_id: int, tc: GeneratedTestCase
    ) -> None:
        """Place a test case into the correct suite(s).

        Every test goes into **Complete Test Cases**.
        Additionally it goes into one of Smoke / Sanity / Regression
        based on its *category* field.
        """
        if not self._folder_map:
            self.setup_folders()

        complete_id = self._folder_map.get("Complete Test Cases")
        if complete_id:
            self._ado.add_test_to_suite(complete_id, test_case_id)
            logger.debug(
                "TC #%s → Complete Test Cases (suite %s)", test_case_id, complete_id
            )

        category = tc.category if tc.category in ("Smoke", "Sanity", "Regression") else "Regression"
        cat_suite_id = self._folder_map.get(category)
        if cat_suite_id:
            self._ado.add_test_to_suite(cat_suite_id, test_case_id)
            logger.debug(
                "TC #%s → %s (suite %s)", test_case_id, category, cat_suite_id
            )

    def assign_many(
        self,
        id_tc_pairs: list[tuple[int, GeneratedTestCase]],
    ) -> None:
        """Convenience: assign a batch of test cases to folders."""
        if not self._folder_map:
            self.setup_folders()
        for tc_id, tc in id_tc_pairs:
            self.assign_test(tc_id, tc)
        logger.info("Assigned %d test cases to folders.", len(id_tc_pairs))
