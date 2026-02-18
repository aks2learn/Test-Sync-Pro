"""
ado_client.py – All Azure DevOps REST / SDK interactions.

Uses the official `azure-devops` Python SDK for work-item operations and
falls back to raw REST (via `requests`) for Test-Plan / Test-Suite endpoints
that the SDK does not fully expose.
"""

from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

import requests
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication

from config import Settings
from models import ExistingTestCase, GeneratedTestCase, TestStep, UserStory

logger = logging.getLogger("test-sync-pro")

# ── XML helpers for the TCM Steps field ─────────────────────────────────

def _steps_xml(steps: list[TestStep]) -> str:
    """Build the XML blob that ADO stores in Microsoft.VSTS.TCM.Steps."""
    root = ET.Element("steps", id="0", last=str(len(steps) + 1))
    for idx, step in enumerate(steps, start=2):
        el = ET.SubElement(root, "step", id=str(idx), type="ValidateStep")
        action = ET.SubElement(el, "parameterizedString", isformatted="true")
        action.text = step.action
        expected = ET.SubElement(el, "parameterizedString", isformatted="true")
        expected.text = step.expected_result
    return ET.tostring(root, encoding="unicode")


def _parse_steps_xml(xml_str: str | None) -> list[TestStep]:
    """Parse the ADO TCM Steps XML back into TestStep objects."""
    if not xml_str:
        return []
    steps: list[TestStep] = []
    try:
        root = ET.fromstring(xml_str)
        for step_el in root.findall("step"):
            params = step_el.findall("parameterizedString")
            action_text = params[0].text or "" if len(params) > 0 else ""
            expected_text = params[1].text or "" if len(params) > 1 else ""
            action_text = _strip_html(action_text)
            expected_text = _strip_html(expected_text)
            steps.append(TestStep(action=action_text, expected_result=expected_text))
    except ET.ParseError:
        logger.warning("Could not parse TCM Steps XML; treating as empty.")
    return steps


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    clean = re.sub(r"<[^>]+>", "", text)
    return html.unescape(clean).strip()


# ── Main client ─────────────────────────────────────────────────────────

class ADOClient:
    """Wraps every ADO interaction needed by Test-Sync-Pro."""

    REQUIRED_FOLDERS = [
        "Complete Test Cases",
        "Regression",
        "Smoke",
        "Sanity",
    ]

    def __init__(self) -> None:
        creds = BasicAuthentication("", Settings.ADO_PAT)
        self._connection = Connection(base_url=Settings.ADO_ORG_URL, creds=creds)
        self._wit = self._connection.clients.get_work_item_tracking_client()
        self._project = Settings.ADO_PROJECT
        self._plan_id = Settings.ADO_TEST_PLAN_ID

        # REST session for endpoints the SDK does not cover
        self._session = requests.Session()
        self._session.auth = ("", Settings.ADO_PAT)
        self._base = f"{Settings.ADO_ORG_URL}/{Settings.ADO_PROJECT}"
        self._org_base = Settings.ADO_ORG_URL
        self._api = "api-version=7.1-preview"
        self._json_header = {"Content-Type": "application/json"}
        self._patch_header = {"Content-Type": "application/json-patch+json"}

    # ── User Story ──────────────────────────────────────────────────────

    def get_user_story(self, story_id: int) -> UserStory:
        """Fetch a single User Story work item by ID."""
        wi = self._wit.get_work_item(story_id, expand="All")
        fields: dict[str, Any] = wi.fields
        return UserStory(
            id=story_id,
            title=fields.get("System.Title", ""),
            description=_strip_html(fields.get("System.Description", "") or ""),
            acceptance_criteria=_strip_html(
                fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", "") or ""
            ),
            priority=int(fields.get("Microsoft.VSTS.Common.Priority", 2)),
            tags=[
                t.strip()
                for t in fields.get("System.Tags", "").split(";")
                if t.strip()
            ],
            state=fields.get("System.State", ""),
        )

    # ── Linked Test Cases ───────────────────────────────────────────────

    def get_linked_test_cases(self, story_id: int) -> list[ExistingTestCase]:
        """Return every Test Case linked to *story_id* via hierarchy."""
        wi = self._wit.get_work_item(story_id, expand="Relations")
        if not wi.relations:
            return []

        tc_ids: list[int] = []
        for rel in wi.relations:
            if "Hierarchy-Forward" in (rel.rel or ""):
                url: str = rel.url
                try:
                    tc_ids.append(int(url.rsplit("/", 1)[-1]))
                except ValueError:
                    continue

        if not tc_ids:
            return []

        results: list[ExistingTestCase] = []
        work_items = self._wit.get_work_items(
            ids=tc_ids, expand="All", error_policy="Omit"
        )
        for item in work_items:
            if item is None:
                continue
            f = item.fields
            if f.get("System.WorkItemType") != "Test Case":
                continue
            results.append(
                ExistingTestCase(
                    id=item.id,
                    title=f.get("System.Title", ""),
                    steps=_parse_steps_xml(
                        f.get("Microsoft.VSTS.TCM.Steps")
                    ),
                    priority=int(f.get("Microsoft.VSTS.Common.Priority", 2)),
                    tags=[
                        t.strip()
                        for t in f.get("System.Tags", "").split(";")
                        if t.strip()
                    ],
                    revision=item.rev or 1,
                )
            )
        return results

    # ── Create / Update Test Case Work Items ────────────────────────────

    def create_test_case(
        self, tc: GeneratedTestCase, story_id: int
    ) -> int:
        """Create a new Test Case work item and link it to the story."""
        bdd_text = f"<b>Given</b> {tc.given}<br><b>When</b> {tc.when}<br><b>Then</b> {tc.then}"

        steps = tc.steps or [
            TestStep(action=f"Given {tc.given}", expected_result="Precondition met"),
            TestStep(action=f"When {tc.when}", expected_result="Action performed"),
            TestStep(action=f"Then {tc.then}", expected_result=tc.then),
        ]

        tags_str = "; ".join(tc.tags) if tc.tags else ""

        document = [
            {"op": "add", "path": "/fields/System.Title", "value": tc.title},
            {
                "op": "add",
                "path": "/fields/System.Description",
                "value": bdd_text,
            },
            {
                "op": "add",
                "path": "/fields/Microsoft.VSTS.TCM.Steps",
                "value": _steps_xml(steps),
            },
            {
                "op": "add",
                "path": "/fields/Microsoft.VSTS.Common.Priority",
                "value": tc.priority,
            },
            {
                "op": "add",
                "path": "/fields/System.Tags",
                "value": tags_str,
            },
            {
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": (
                        f"{self._org_base}/_apis/wit/workItems/{story_id}"
                    ),
                    "attributes": {"comment": "Linked by Test-Sync-Pro"},
                },
            },
        ]

        url = (
            f"{self._base}/_apis/wit/workitems/$Test%20Case?{self._api}"
        )
        resp = self._session.patch(
            url, json=document, headers=self._patch_header
        )
        resp.raise_for_status()
        new_id = resp.json()["id"]
        logger.info("Created Test Case #%s  →  '%s'", new_id, tc.title)
        return new_id

    def update_test_case(
        self, tc_id: int, tc: GeneratedTestCase
    ) -> None:
        """Patch an existing Test Case with refreshed content."""
        bdd_text = f"<b>Given</b> {tc.given}<br><b>When</b> {tc.when}<br><b>Then</b> {tc.then}"

        steps = tc.steps or [
            TestStep(action=f"Given {tc.given}", expected_result="Precondition met"),
            TestStep(action=f"When {tc.when}", expected_result="Action performed"),
            TestStep(action=f"Then {tc.then}", expected_result=tc.then),
        ]

        tags_str = "; ".join(tc.tags) if tc.tags else ""

        document = [
            {"op": "replace", "path": "/fields/System.Title", "value": tc.title},
            {
                "op": "replace",
                "path": "/fields/System.Description",
                "value": bdd_text,
            },
            {
                "op": "replace",
                "path": "/fields/Microsoft.VSTS.TCM.Steps",
                "value": _steps_xml(steps),
            },
            {
                "op": "replace",
                "path": "/fields/Microsoft.VSTS.Common.Priority",
                "value": tc.priority,
            },
            {
                "op": "replace",
                "path": "/fields/System.Tags",
                "value": tags_str,
            },
        ]

        url = f"{self._base}/_apis/wit/workitems/{tc_id}?{self._api}"
        resp = self._session.patch(
            url, json=document, headers=self._patch_header
        )
        resp.raise_for_status()
        logger.info("Updated Test Case #%s  →  '%s'", tc_id, tc.title)

    # ── Test Plan / Suite (folder) management ───────────────────────────

    def _get_root_suite_id(self) -> int:
        """Return the root suite ID for the configured Test Plan."""
        url = (
            f"{self._base}/_apis/testplan/Plans/{self._plan_id}"
            f"?{self._api}"
        )
        resp = self._session.get(url)
        resp.raise_for_status()
        return resp.json()["rootSuite"]["id"]

    def _list_child_suites(self, parent_suite_id: int) -> dict[str, int]:
        """Return {name: id} of all immediate child suites."""
        url = (
            f"{self._base}/_apis/testplan/Plans/{self._plan_id}"
            f"/Suites?{self._api}"
        )
        resp = self._session.get(url)
        resp.raise_for_status()
        all_suites = resp.json().get("value", []) or []
        return {
            s["name"]: s["id"]
            for s in all_suites
            if s.get("parentSuite", {}).get("id") == parent_suite_id
        }

    def _create_static_suite(
        self, parent_suite_id: int, name: str
    ) -> int:
        """Create a static (folder) suite under *parent_suite_id*."""
        url = (
            f"{self._base}/_apis/testplan/Plans/{self._plan_id}"
            f"/Suites?{self._api}"
        )
        body = {
            "suiteType": "staticTestSuite",
            "name": name,
            "parentSuite": {"id": parent_suite_id},
        }
        resp = self._session.post(url, json=body, headers=self._json_header)
        resp.raise_for_status()
        suite_id = resp.json()["id"]
        logger.info("Created suite '%s' (id=%s)", name, suite_id)
        return suite_id

    def ensure_folders(self) -> dict[str, int]:
        """Guarantee the four required folders exist; return {name: id}."""
        root_id = self._get_root_suite_id()
        existing = self._list_child_suites(root_id)
        folder_map: dict[str, int] = {}

        for folder in self.REQUIRED_FOLDERS:
            if folder in existing:
                folder_map[folder] = existing[folder]
                logger.info("Suite '%s' already exists (id=%s)", folder, existing[folder])
            else:
                folder_map[folder] = self._create_static_suite(root_id, folder)

        return folder_map

    def add_test_to_suite(self, suite_id: int, test_case_id: int) -> None:
        """Add a Test Case to a Test Suite (folder)."""
        url = (
            f"{self._base}/_apis/testplan/Plans/{self._plan_id}"
            f"/Suites/{suite_id}/TestCase?{self._api}"
        )
        body = [{"workItem": {"id": test_case_id}}]
        resp = self._session.post(url, json=body, headers=self._json_header)
        resp.raise_for_status()
        logger.debug("Added TC #%s to suite %s", test_case_id, suite_id)
