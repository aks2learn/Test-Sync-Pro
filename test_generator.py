"""
test_generator.py – AI-powered BDD test-case generation (multi-provider).

Supported providers:
  • OpenAI, Groq, DeepSeek, Mistral, Together AI, Google Gemini,
    Ollama, LM Studio, any custom OpenAI-compatible endpoint
    → routed through the `openai` SDK
  • Anthropic Claude
    → routed through the native `anthropic` SDK
  • Azure OpenAI
    → routed through the `openai` SDK's AzureOpenAI client

The LLM_PROVIDER env var selects which path is used.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import AzureOpenAI, OpenAI

from config import Settings
from models import GeneratedTestCase, TestStep, UserStory

logger = logging.getLogger("test-sync-pro")

# ── System prompt that governs the LLM's output ────────────────────────

SYSTEM_PROMPT = """\
You are a Senior QA Automation Engineer with deep expertise in BDD and
Azure DevOps.  Your job is to generate **comprehensive** test cases for
a given User Story.

### Rules
1. Use **Given-When-Then** (Gherkin) syntax for every test case.
2. Cover three categories:
   • **Positive** – happy-path flows that satisfy the Acceptance Criteria.
   • **Negative** – invalid inputs, unauthorized access, error conditions.
   • **Edge**     – boundary values, empty/null fields, concurrency, limits.
3. Apply Boundary Value Analysis for every numeric / date / length
   constraint mentioned in the Acceptance Criteria.
4. Ensure **100 % coverage** of every distinct Acceptance Criterion.
5. Assign a **Priority** (1 = Critical, 2 = High, 3 = Medium, 4 = Low)
   based on business impact inferred from the story.
6. Tag each test with one or more of: Smoke, Sanity, Regression.
   • **Smoke** → core functionality that must never break.
   • **Sanity** → quick confidence check after a build.
   • **Regression** → full coverage for release sign-off.
7. Set "category" to the **primary** folder the test belongs to
   (one of: "Smoke", "Sanity", "Regression").
8. For each test case, also produce concrete **steps** (action + expected
   result pairs) that translate the Given-When-Then into manual test steps.

### Output format  (strict JSON array – no markdown fences)
[
  {
    "title": "Verify <concise test objective>",
    "given": "Given <precondition>",
    "when":  "When <action>",
    "then":  "Then <expected outcome>",
    "steps": [
      {"action": "<what the tester does>", "expected_result": "<what should happen>"}
    ],
    "priority": 2,
    "tags": ["Regression"],
    "category": "Regression",
    "test_type": "Positive"
  }
]

Return ONLY the JSON array.  No explanation, no markdown.
"""


def _build_user_prompt(story: UserStory, delta_hint: str = "") -> str:
    """Compose the user-role message for the LLM."""
    parts = [
        f"## User Story #{story.id}",
        f"**Title:** {story.title}",
        f"**Description:** {story.description}",
        f"**Acceptance Criteria:**\n{story.acceptance_criteria}",
        f"**Story Priority:** {story.priority}",
    ]
    if story.tags:
        parts.append(f"**Tags:** {', '.join(story.tags)}")
    if delta_hint:
        parts.append(
            f"\n### Delta (new / changed requirements only)\n{delta_hint}\n"
            "Generate test cases ONLY for the delta above."
        )
    return "\n\n".join(parts)


# ── Response parsing ────────────────────────────────────────────────────

def _parse_response(raw: str) -> list[GeneratedTestCase]:
    """Parse the LLM JSON response into GeneratedTestCase objects."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        items: list[dict[str, Any]] = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("LLM returned invalid JSON: %s\n---\n%s", exc, raw[:500])
        raise ValueError("LLM response is not valid JSON") from exc

    cases: list[GeneratedTestCase] = []
    for obj in items:
        steps = [
            TestStep(action=s["action"], expected_result=s["expected_result"])
            for s in obj.get("steps", [])
        ]
        cases.append(
            GeneratedTestCase(
                title=obj["title"],
                given=obj["given"],
                when=obj["when"],
                then=obj["then"],
                steps=steps,
                priority=int(obj.get("priority", 2)),
                tags=obj.get("tags", ["Regression"]),
                category=obj.get("category", "Regression"),
                test_type=obj.get("test_type", "Positive"),
            )
        )
    return cases


# ── Provider-specific callers ───────────────────────────────────────────

def _call_openai_compatible(
    client: OpenAI, model: str, user_msg: str
) -> str:
    """Shared call logic for OpenAI and every OpenAI-compatible provider."""
    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    return response.choices[0].message.content or ""


def _call_anthropic(client: Any, model: str, user_msg: str) -> str:
    """Call Anthropic's native messages API."""
    response = client.messages.create(
        model=model,
        max_tokens=8192,
        temperature=0.2,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return response.content[0].text


# ── Public API ──────────────────────────────────────────────────────────

class TestGenerator:
    """Generates BDD test cases by calling the configured LLM provider."""

    def __init__(self) -> None:
        provider = Settings.LLM_PROVIDER

        if provider == "azure_openai":
            self._provider = "openai_compat"
            self._openai = AzureOpenAI(
                azure_endpoint=Settings.AZURE_OPENAI_ENDPOINT,
                api_key=Settings.AZURE_OPENAI_API_KEY,
                api_version=Settings.AZURE_OPENAI_API_VERSION,
            )
            self._model = Settings.AZURE_OPENAI_DEPLOYMENT
            logger.info("LLM provider: Azure OpenAI  (deployment=%s)", self._model)

        elif provider == "anthropic":
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "LLM_PROVIDER=anthropic requires the 'anthropic' package.\n"
                    "  → Run: pip install anthropic"
                )
            self._provider = "anthropic"
            self._anthropic = anthropic.Anthropic(api_key=Settings.LLM_API_KEY)
            self._model = Settings.LLM_MODEL
            logger.info("LLM provider: Anthropic  (model=%s)", self._model)

        else:
            self._provider = "openai_compat"
            base_url = Settings.resolved_base_url()
            kwargs: dict[str, Any] = {"api_key": Settings.LLM_API_KEY}
            if base_url:
                kwargs["base_url"] = base_url
            self._openai = OpenAI(**kwargs)
            self._model = Settings.LLM_MODEL
            label = provider if provider != "openai" else "OpenAI"
            logger.info(
                "LLM provider: %s  (model=%s%s)",
                label,
                self._model,
                f", base_url={base_url}" if base_url else "",
            )

    def generate(
        self,
        story: UserStory,
        delta_hint: str = "",
    ) -> list[GeneratedTestCase]:
        """Call the configured LLM and return parsed test cases."""
        user_msg = _build_user_prompt(story, delta_hint)
        logger.info("Sending prompt to LLM (%d chars)…", len(user_msg))

        if self._provider == "anthropic":
            raw = _call_anthropic(self._anthropic, self._model, user_msg)
        else:
            raw = _call_openai_compatible(self._openai, self._model, user_msg)

        logger.debug("LLM response length: %d chars", len(raw))
        cases = _parse_response(raw)
        logger.info("Generated %d test cases", len(cases))
        return cases
