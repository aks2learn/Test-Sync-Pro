# Test-Sync-Pro

**AI-powered BDD Test-Case Agent for Azure DevOps**

Test-Sync-Pro reads an Azure DevOps (ADO) User Story, uses an AI model to generate comprehensive **Given-When-Then** test cases, and pushes them back into ADO — complete with folder organisation, priority tagging, hierarchy links, and smart de-duplication.

Calls your AI provider **directly** — no proxy, no middleman. Supports **OpenAI, Anthropic Claude, Azure OpenAI, Groq, DeepSeek, Mistral, Together AI, Google Gemini, Ollama, LM Studio**, and any custom OpenAI-compatible endpoint.

---

## What It Does (In Plain English)

1. You give it a **User Story ID** from Azure DevOps.
2. It fetches the story's Title, Description, and Acceptance Criteria.
3. If test cases already exist for that story, it figures out what's **new or changed** (the "delta").
4. An AI model generates test cases in **BDD format** (Given / When / Then) covering:
   - **Positive** scenarios (happy path)
   - **Negative** scenarios (error handling)
   - **Edge cases** (boundary values, limits)
5. Before creating anything, it checks for **duplicates** (90% similarity threshold).
6. New tests are created in ADO; near-duplicates update the existing work item.
7. Every test is filed into the correct folder: `Complete Test Cases`, `Smoke`, `Sanity`, or `Regression`.
8. Tests are linked to the User Story using ADO's `System.LinkTypes.Hierarchy-Forward` link type.

---

## Prerequisites

| Requirement | Details |
|---|---|
| **Python** | 3.10 or higher ([download](https://www.python.org/downloads/)) |
| **Azure DevOps account** | With a project that has Test Plans enabled |
| **ADO Personal Access Token (PAT)** | Scopes required: **Work Items (Read & Write)**, **Test Management (Read & Write)** |
| **LLM API key** | From any supported provider (OpenAI, Anthropic, Groq, DeepSeek, Mistral, etc.) |
| **pip** | Comes with Python — used to install dependencies |

### How to Create an ADO Personal Access Token

1. Open Azure DevOps → click your **profile icon** (top-right) → **Personal access tokens**.
2. Click **+ New Token**.
3. Give it a name (e.g. `test-sync-pro`).
4. Under **Scopes**, select:
   - **Work Items** → Read & Write
   - **Test Management** → Read & Write
5. Click **Create** and **copy the token immediately**.

---

## Setup (Step by Step)

### Step 1 — Clone or Download

```bash
# If you have git:
git clone <your-repo-url>
cd AI_Agent_TC_creation

# Or simply download and unzip the project folder.
```

### Step 2 — Create a Virtual Environment (recommended)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Configure Environment Variables

Copy the example file and fill in your values:

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Open `.env` in any text editor and fill in **every** value:

```dotenv
# Azure DevOps
ADO_ORG_URL=https://dev.azure.com/your-org
ADO_PROJECT=YourProjectName
ADO_PAT=paste-your-pat-here
ADO_TEST_PLAN_ID=12345

# LLM — pick your provider
LLM_PROVIDER=openai
LLM_API_KEY=your-api-key-here
LLM_MODEL=gpt-4o
```

> **Finding your Test Plan ID:** Open your Test Plan in ADO. The URL looks like
> `https://dev.azure.com/org/project/_testPlans/define?planId=12345` — the number
> after `planId=` is what you need.

### Choosing an LLM Provider

Set `LLM_PROVIDER` to one of the values below. The agent calls each provider **directly** using its native SDK — no proxy or middleman.

| `LLM_PROVIDER` | Provider | `LLM_API_KEY` | Example `LLM_MODEL` |
|---|---|---|---|
| `openai` | **OpenAI** *(default)* | `sk-...` | `gpt-4o` |
| `anthropic` | **Anthropic Claude** | `sk-ant-...` | `claude-sonnet-4-20250514` |
| `groq` | **Groq** | `gsk_...` | `llama-3.3-70b-versatile` |
| `deepseek` | **DeepSeek** | `sk-...` | `deepseek-chat` |
| `mistral` | **Mistral** | `...` | `mistral-large-latest` |
| `together` | **Together AI** | `...` | `meta-llama/Llama-3-70b` |
| `google` | **Google Gemini** | `AIza...` | `gemini-2.0-flash` |
| `ollama` | **Ollama** (local) | `ollama` | `llama3` |
| `lmstudio` | **LM Studio** (local) | `lm-studio` | *(auto-detected)* |
| `azure_openai` | **Azure OpenAI** | Use the `AZURE_OPENAI_*` variables (see `.env.example`) | — |
| `custom` | Any OpenAI-compatible API | `...` | `...` (also set `LLM_BASE_URL`) |

**Examples** — just these 3 lines in your `.env` change the entire provider:

```dotenv
# ── Anthropic Claude ──
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-your-key
LLM_MODEL=claude-sonnet-4-20250514

# ── Groq (fast Llama) ──
# LLM_PROVIDER=groq
# LLM_API_KEY=gsk_your-key
# LLM_MODEL=llama-3.3-70b-versatile

# ── Local Ollama (free, offline) ──
# LLM_PROVIDER=ollama
# LLM_API_KEY=ollama
# LLM_MODEL=llama3
```

---

## Running the Agent

### Basic Usage

```bash
python run.py --id 12345
```

Replace `12345` with your actual ADO **User Story Work-Item ID**.

### Dry Run (preview without writing to ADO)

```bash
python run.py --id 12345 --dry-run
```

This generates and displays the test cases but does **not** create or update anything in ADO. Great for previewing what the agent will do.

### Verbose Mode (debug logging)

```bash
python run.py --id 12345 --verbose
```

### Combine Flags

```bash
python run.py --id 12345 --dry-run --verbose
```

---

## What Happens When You Run It

```
┌─────────────────────────────────────────────────────────────┐
│  Test-Sync-Pro  –  AI-powered BDD Test-Case Agent           │
└─────────────────────────────────────────────────────────────┘

─── Phase 1 · Fetch User Story ──────────────────────────────
  → Fetches story title, description, acceptance criteria
  → Finds existing linked test cases

─── Phase 2 · Delta Analysis ────────────────────────────────
  → Compares acceptance criteria with existing test steps
  → Identifies uncovered requirements

─── Phase 3 · Generate Test Cases ───────────────────────────
  → AI generates Given-When-Then test cases
  → Covers Positive, Negative, and Edge scenarios

─── Phase 4 · De-duplication ────────────────────────────────
  → Checks each new test against existing ones
  → ≥90% similar = update existing instead of creating new

─── Phase 5 · Push to Azure DevOps ──────────────────────────
  → Creates/updates test case work items
  → Links to User Story (Hierarchy-Forward)
  → Files into folders: Complete Test Cases, Smoke, Sanity, Regression
```

---

## Folder Structure in ADO

Under your Test Plan, the agent creates four suites (folders):

```
Test Plan
├── Complete Test Cases    ← every generated test goes here
├── Smoke                  ← core happy-path tests
├── Sanity                 ← quick confidence checks
└── Regression             ← full coverage tests
```

---

## Project Files

| File | Purpose |
|---|---|
| `run.py` | CLI entry point — orchestrates everything |
| `config.py` | Loads and validates `.env` settings |
| `models.py` | Data classes (UserStory, TestStep, GeneratedTestCase, etc.) |
| `ado_client.py` | All Azure DevOps API interactions |
| `test_generator.py` | Multi-provider BDD test-case generation |
| `delta_analyzer.py` | Identifies new/changed acceptance criteria |
| `dedup_engine.py` | 90% similarity check to avoid duplicates |
| `folder_manager.py` | Manages the 4-folder hierarchy in Test Plans |
| `.env.example` | Template for your environment variables |
| `requirements.txt` | Python package dependencies |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `Missing required environment variables` | Make sure you copied `.env.example` to `.env` and filled in all values |
| `401 Unauthorized` | Your PAT is invalid or expired — generate a new one |
| `403 Forbidden` | Your PAT doesn't have the required scopes (Work Items + Test Management) |
| `404 Not Found` | Check `ADO_ORG_URL`, `ADO_PROJECT`, and that the Work Item ID exists |
| `LLM returned invalid JSON` | Try again — occasionally GPT returns malformed JSON. The agent retries automatically |
| `Test Plan ID 0` | Set `ADO_TEST_PLAN_ID` in your `.env` file |

---

## Customisation

- **Similarity threshold:** Change `DEDUP_THRESHOLD` in `.env` (0.0 to 1.0).
- **AI model:** Change `LLM_MODEL` in `.env` (e.g. `gpt-4o-mini` for lower cost).
- **Switch providers:** Change `LLM_PROVIDER` and `LLM_API_KEY` — that's it.
- **Local LLMs:** Set `LLM_PROVIDER=ollama` or `LLM_PROVIDER=lmstudio` for fully offline operation.

---

## License

This project is provided as-is for internal use. Modify freely to suit your organisation's needs.
