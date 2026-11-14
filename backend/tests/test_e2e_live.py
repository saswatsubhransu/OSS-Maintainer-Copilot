import urllib.request
import json
import sys

BASE_URL = "http://127.0.0.1:8000"

def post(endpoint, data, headers=None):
    url = f"{BASE_URL}{endpoint}"
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=req_headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def get(endpoint):
    url = f"{BASE_URL}{endpoint}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def main():
    print("Testing live backend at", BASE_URL)
    
    # 1. Health
    status, data = get("/health")
    assert status == 200, f"Health check failed: {status}"
    assert data["status"] == "ok"
    print("✓ GET /health PASSED")

    # 2. Triage Categorization
    status, data = post("/api/triage", {
        "title": "Severe memory leak in websocket connection handler",
        "body": "After 10k connections, memory grows indefinitely without releasing.\n```traceback\nLeak at socket.py:42\n```"
    })
    assert status == 200
    assert data["category"] in ["performance", "bug"]
    assert "summary" in data
    print(f"✓ POST /api/triage PASSED (category: {data['category']}, priority: {data['priority']})")

    # 3. Duplicate Detection
    status, data = post("/api/duplicates", {
        "target_issue": {
            "number": 50,
            "title": "Severe memory leak in websocket connection handler",
            "body": "Memory increases rapidly when opening multiple websockets."
        },
        "candidate_issues": [
            {
                "number": 12,
                "title": "Websocket connection memory leak over time",
                "body": "Long-lived websocket sessions cause OOM crash.",
                "state": "open",
                "html_url": "https://github.com/foo/bar/issues/12"
            },
            {
                "number": 14,
                "title": "Fix typo in tutorial documentation",
                "body": "Typo in installation step.",
                "state": "closed",
                "html_url": "https://github.com/foo/bar/issues/14"
            }
        ],
        "threshold": 0.25
    })
    assert status == 200
    assert data["has_duplicates"] is True
    assert data["top_matches"][0]["issue_number"] == 12
    print(f"✓ POST /api/duplicates PASSED (found top match #{data['top_matches'][0]['issue_number']} with {int(data['top_matches'][0]['similarity_score']*100)}% similarity)")

    # 4. PR Summarization
    status, data = post("/api/summarize-pr", {
        "number": 77,
        "title": "feat: add JWT token rotation and blacklist cache",
        "body": "Implements automated refresh token rotation with redis blacklist.",
        "author": "security-dev",
        "files": [
            {"filename": "app/auth/jwt.py", "status": "modified", "additions": 80, "deletions": 10},
            {"filename": "app/config.py", "status": "modified", "additions": 5, "deletions": 0}
        ]
    })
    assert status == 200
    assert "tldr" in data
    assert len(data["key_changes"]) > 0
    print(f"✓ POST /api/summarize-pr PASSED (risk: {data['risk_level']})")

    # 5. Missing Tests & Docs Audit
    status, data = post("/api/audit-pr", {
        "number": 77,
        "title": "feat: add JWT token rotation and blacklist cache",
        "body": "New feature.",
        "files": [
            {"filename": "app/auth/jwt.py", "status": "added", "additions": 80, "deletions": 0}
        ]
    })
    assert status == 200
    assert data["readiness"] in ["Needs Tests", "Needs Tests & Docs"]
    assert len(data["suggested_test_scaffold"]) > 0
    print(f"✓ POST /api/audit-pr PASSED (readiness: {data['readiness']}, test_status: {data['test_status']})")

    # 6. Release Notes
    status, data = post("/api/release-notes", {
        "owner": "oss",
        "repo": "maintainer-copilot",
        "current_version": "v1.0.0",
        "pull_requests": [
            {"number": 10, "title": "feat: duplicate issue detection engine", "author": "dev1", "labels": ["enhancement"]},
            {"number": 11, "title": "fix: prevent timeout on large git diffs", "author": "dev2", "labels": ["bug"]}
        ]
    })
    assert status == 200
    assert data["bump_type"] == "minor"
    assert data["recommended_version"] == "v1.1.0"
    print(f"✓ POST /api/release-notes PASSED (recommended: {data['recommended_version']})")

    # 7. Webhook Handler
    status, data = post("/api/webhooks/github", {
        "action": "opened",
        "issue": {
            "number": 101,
            "title": "Bug: Crash when uploading avatar image",
            "body": "Throws 500 error on .png files.",
            "labels": [{"name": "bug"}]
        }
    }, headers={"X-GitHub-Event": "issues"})
    assert status == 200
    assert data["handled"] is True
    print("✓ POST /api/webhooks/github PASSED")

    print("\n🎉 ALL LIVE ENDPOINTS PASSED PRE-DEPLOYMENT TESTS!")

if __name__ == "__main__":
    main()
