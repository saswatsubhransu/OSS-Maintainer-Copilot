import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "issue_categorization" in data["features"]
    assert "duplicate_detection" in data["features"]
    assert "pr_summarization" in data["features"]
    assert "test_and_docs_audit" in data["features"]
    assert "release_notes_generator" in data["features"]


def test_triage_categorization():
    payload = {
        "title": "Crash on startup: NullPointerException in auth token parser",
        "body": "When launching the server with an invalid JWT, it throws an uncaught exception.\n```\nTraceback...\n```",
    }
    res = client.post("/api/triage", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["category"] in ["bug", "security"]
    assert data["priority"] in ["high", "urgent"]
    assert "bug" in data["suggested_labels"] or "component:auth" in data["suggested_labels"]
    assert len(data["next_steps"]) > 0


def test_duplicate_detection():
    target = {
        "number": 105,
        "title": "Crash on startup: NullPointerException in auth token parser",
        "body": "Server fails to start with null pointer exception in auth module.",
    }
    candidates = [
        {
            "number": 101,
            "title": "Startup crash: NullPointerException in auth token parser",
            "body": "NullPointerException when parsing auth tokens on server boot.",
            "state": "open",
            "html_url": "https://github.com/foo/bar/issues/101",
            "labels": ["bug"],
        },
        {
            "number": 102,
            "title": "Documentation typo in README quickstart",
            "body": "Fixed spelling of configuration in getting started guide.",
            "state": "closed",
            "html_url": "https://github.com/foo/bar/issues/102",
            "labels": ["documentation"],
        },
    ]

    res = client.post(
        "/api/duplicates",
        json={"target_issue": target, "candidate_issues": candidates, "threshold": 0.25},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["has_duplicates"] is True
    assert len(data["top_matches"]) > 0
    assert data["top_matches"][0]["issue_number"] == 101


def test_pr_summary():
    payload = {
        "number": 42,
        "title": "feat(auth): add OAuth2 refresh token rotation",
        "body": "Implements refresh token rotation to enhance session security.",
        "author": "alice",
        "files": [
            {"filename": "app/auth/tokens.py", "status": "modified", "additions": 45, "deletions": 5},
            {"filename": "app/config.py", "status": "modified", "additions": 10, "deletions": 2},
        ],
    }
    res = client.post("/api/summarize-pr", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["number"] == 42
    assert "OAuth2 refresh token" in data["tldr"]
    assert len(data["key_changes"]) > 0
    assert data["risk_level"] in ["medium", "high"]


def test_missing_tests_and_docs_audit():
    # Source code added without tests or docs
    payload = {
        "number": 99,
        "title": "Add payment gateway webhook handler",
        "body": "New endpoint for stripe webhooks.",
        "files": [
            {"filename": "backend/app/payments.py", "status": "added", "additions": 120, "deletions": 0},
            {"filename": "backend/app/config.py", "status": "modified", "additions": 8, "deletions": 1},
        ],
    }
    res = client.post("/api/audit-pr", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["readiness"] in ["Needs Tests", "Needs Tests & Docs"]
    assert data["test_status"] == "missing"
    assert len(data["suggested_test_scaffold"]) > 0


def test_release_notes_generation():
    prs = [
        {"number": 1, "title": "feat: add dark mode theme toggle", "author": "dev1", "labels": ["enhancement"]},
        {"number": 2, "title": "fix: resolve memory leak in websocket listener", "author": "dev2", "labels": ["bug"]},
        {"number": 3, "title": "docs: update API authentication guide", "author": "writer1", "labels": ["documentation"]},
    ]
    payload = {
        "owner": "acme",
        "repo": "awesome-project",
        "current_version": "v1.2.0",
        "pull_requests": prs,
    }
    res = client.post("/api/release-notes", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["bump_type"] == "minor"
    assert data["recommended_version"] == "v1.3.0"
    assert len(data["features"]) == 1
    assert len(data["bug_fixes"]) == 1
    assert len(data["documentation"]) == 1
    assert "dev1" in data["contributors"]
    assert "# Release v1.3.0" in data["markdown"]


def test_github_webhook():
    webhook_payload = {
        "action": "opened",
        "issue": {
            "number": 88,
            "title": "Bug: unable to save settings on Safari",
            "body": "Clicking save does not trigger request.",
            "labels": [{"name": "bug"}],
        },
    }
    res = client.post(
        "/api/webhooks/github",
        json=webhook_payload,
        headers={"X-GitHub-Event": "issues"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["handled"] is True
    assert "Auto-triaged Issue #88" in data["summary"]
