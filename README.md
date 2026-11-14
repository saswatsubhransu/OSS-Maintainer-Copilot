# OSS Maintainer Copilot

**OSS Maintainer Copilot** is a developer platform and GitHub App designed to solve open-source maintainer burnout by automating triage, duplicate detection, pull request reviews, test/docs audits, and release preparation.

---

## 🌟 Core Copilot Capabilities

### 1. 🏷️ Categorize GitHub Issues Automatically
- **Multi-class taxonomy**: Automatically classifies incoming issues into `bug`, `feature_request`, `documentation`, `performance`, `security`, `question`, or `maintenance`.
- **Priority & Component scoring**: Assigns urgency (`low`, `medium`, `high`, `urgent`) and extracts the affected component (e.g. `api`, `auth`, `ui`, `database`, `cli`).
- **Standard Label Suggestions**: Generates conventional kebab-case labels (`bug`, `needs-repro`, `priority/high`).
- **Explainable Triage**: Highlights missing reproduction steps, stack traces, and environment details.
- **Maintainer Draft Reply**: Formulates polite, constructive responses ready to post to issue authors.

### 2. 🔍 Detect Possible Duplicate Issues
- **Dual-layer similarity radar**: Combines title token overlap, TF-IDF / term-frequency cosine similarity, and error message / code token fingerprinting.
- **Duplicate Confidence & Scoring**: Scores issues from 0% to 100% duplicate probability.
- **Matching Signals & Distinctions**: Details shared error signatures (e.g. `NullPointerException`, identical tracebacks) and highlights critical differences (e.g. tested version or OS).
- **Maintainer Recommendations**: Actionable guidance such as *"Probable duplicate: close as duplicate of #X"*, *"Cross-link issues"*, or *"Independent root cause"*.

### 3. 🔀 Summarize Pull Requests
- **Executive TL;DR**: 1-2 sentence high-level overview of what the PR accomplishes and why.
- **Domain & Component Breakdown**: Groups file modifications by architecture tier (core source, test suite, infrastructure/config).
- **Architectural & Design Impact**: Evaluates schema changes, database migrations, and public route alterations.
- **Breaking Change Detection**: Flags backward-incompatible API changes, deprecated parameters, and config updates.
- **Risk Assessment**: Categorizes risk (`LOW`, `MEDIUM`, `HIGH`) with specific justification.
- **Reviewer Checklist**: Generates targeted verification checkpoints for human maintainers.

### 4. 🧪 Identify Missing Tests and Documentation
- **Test Coverage Auditor**: Inspects PR file changes to check if core application logic has been modified without corresponding unit or integration test files (`test_*.py`, `*.test.ts`, `spec/`).
- **Documentation Auditor**: Checks whether public API changes, new CLI flags, or environment variables have matching documentation updates in `README.md` or docstrings.
- **Readiness Classification**: Classifies PRs as `Ready for Review`, `Needs Tests`, `Needs Docs`, or `Needs Tests & Docs`.
- **Scaffold Generators**: Automatically drafts copy-pasteable unit test scaffold code (Pytest, Vitest/Jest) and Markdown documentation blocks.

### 5. 📦 Generate Release Notes
- **Conventional Categorization**: Automatically clusters merged pull requests into standard changelog sections:
  - 🚀 Features & Enhancements
  - 🐛 Bug Fixes
  - ⚠️ Breaking Changes & Deprecations
  - 📚 Documentation Updates
  - 🛠️ Maintenance & Chores
- **SemVer Bump Calculator**: Recommends the next semantic version (`Major`, `Minor`, or `Patch`) based on whether breaking changes or new features were introduced.
- **Contributor Attribution**: Automatically extracts and thanks community contributors.
- **Export & Publish**: Generates GitHub Release-ready Markdown with 1-click clipboard copy.

### 6. ⚡ GitHub App & Webhook Automation
- Supports live GitHub webhook delivery via `POST /api/webhooks/github`.
- Verifies GitHub HMAC-SHA256 signatures (`X-Hub-Signature-256`).
- Automatically handles `issues` (`opened`) and `pull_request` (`opened`, `synchronize`).
- Includes an interactive in-dashboard Webhook Simulator for local testing without deploying.

---

## 🏗️ Architecture & Tech Stack

```
┌────────────────────────────────────────────────────────┐
│                   Next.js Frontend                     │
│  - Issue Categorizer Tab      - Duplicate Radar Tab    │
│  - PR Summarizer Tab          - Test & Docs Audit Tab  │
│  - Release Notes Tab          - Webhook Simulator Tab  │
└───────────────────────────▲────────────────────────────┘
                            │ REST APIs
┌───────────────────────────▼────────────────────────────┐
│                    FastAPI Backend                     │
│  ├── /api/repos/.../issues   ├── /api/triage           │
│  ├── /api/repos/.../pulls    ├── /api/duplicates       │
│  ├── /api/summarize-pr       ├── /api/audit-pr         │
│  ├── /api/release-notes      ├── /api/webhooks/github  │
└─────────────┬───────────────────────────┬──────────────┘
              │                           │
              ▼                           ▼
    GitHub REST API v3           AI & Heuristic Engine
  (Issues, Pulls, Patches)      (OpenAI SDK + Algorithmic
                                  Fallback Scorer)
```

- **Backend**: Python 3.9+, FastAPI, Pydantic v2, Uvicorn, HTTPX, OpenAI Python SDK
- **Frontend**: Next.js 15 (App Router), React 19, TypeScript
- **GitHub**: GitHub REST API v3 + Webhooks HMAC-SHA256

---

## 🚀 Quickstart Guide

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
```

Edit `backend/.env` (optional for local testing, algorithmic fallbacks work out of the box):
```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
GITHUB_TOKEN=your_personal_access_token_here   # Recommended for 5,000 req/hr rate limit
GITHUB_WEBHOOK_SECRET=your_webhook_secret_here
FRONTEND_ORIGIN=http://localhost:3000
```

Start the backend server:
```bash
uvicorn app.main:app --reload --port 8000
```
Interactive API Swagger docs: http://localhost:8000/docs

### 2. Frontend Setup

In a new terminal window:
```bash
cd frontend
npm install
npm run dev
```

Open your browser to: **http://localhost:3000**

---

## 🧪 Running Tests

Run the full backend test suite covering all 5 copilot capabilities:

```bash
cd backend
source .venv/bin/activate
PYTHONPATH=. pytest tests/
```

Or run the zero-dependency service test runner:
```bash
PYTHONPATH=backend python3 backend/tests/run_tests.py
```

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check & feature status |
| `GET` | `/api/repos/{owner}/{repo}/issues` | List repository open issues |
| `GET` | `/api/repos/{owner}/{repo}/pulls` | List repository pull requests |
| `GET` | `/api/repos/{owner}/{repo}/pulls/{number}/files` | List changed files and diff patches |
| `GET` | `/api/repos/{owner}/{repo}/merged-prs` | List merged PRs for release notes |
| `POST` | `/api/triage` | Categorize issue & generate next steps |
| `POST` | `/api/duplicates` | Detect potential duplicate issues with match score |
| `POST` | `/api/summarize-pr` | Generate PR executive summary, breaking changes & risk |
| `POST` | `/api/audit-pr` | Audit PR for missing tests & docs with scaffold generators |
| `POST` | `/api/release-notes` | Generate SemVer release notes from merged PRs |
| `POST` | `/api/webhooks/github` | Handle GitHub App webhooks with signature verification |
