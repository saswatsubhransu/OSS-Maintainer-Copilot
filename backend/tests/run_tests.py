import sys
import unittest
from app.schemas import (
    TriageRequest,
    DuplicateDetectRequest,
    IssueItem,
    PRSummaryRequest,
    PRFileItem,
    PRAuditRequest,
    ReleaseNotesRequest,
    ClosedPRItem,
)
from app.services.triage import analyze_issue
from app.services.duplicate import detect_duplicates
from app.services.pr_summary import summarize_pull_request
from app.services.audit import audit_pull_request
from app.services.release_notes import generate_release_notes


class TestCopilotServices(unittest.TestCase):
    def test_categorize_issue(self):
        req = TriageRequest(
            title="Crash on startup: NullPointerException in auth token parser",
            body="When launching the server with an invalid JWT, it throws an uncaught exception.\n```\nTraceback...\n```",
        )
        res = analyze_issue(req)
        self.assertIn(res.category, ["bug", "security"])
        self.assertIn(res.priority, ["high", "urgent"])
        self.assertTrue(len(res.next_steps) > 0)
        self.assertTrue(len(res.suggested_labels) > 0)

    def test_detect_duplicates(self):
        target = IssueItem(
            number=105,
            title="Crash on startup: NullPointerException in auth token parser",
            body="Server fails to start with null pointer exception in auth module.",
        )
        candidates = [
            IssueItem(
                number=101,
                title="Startup crash: NullPointerException in auth token parser",
                body="NullPointerException when parsing auth tokens on server boot.",
                state="open",
            ),
            IssueItem(
                number=102,
                title="Documentation typo in README quickstart",
                body="Fixed spelling of configuration in getting started guide.",
                state="closed",
            ),
        ]
        res = detect_duplicates(DuplicateDetectRequest(target_issue=target, candidate_issues=candidates, threshold=0.25))
        self.assertTrue(res.has_duplicates)
        self.assertEqual(res.top_matches[0].issue_number, 101)
        self.assertGreaterEqual(res.top_matches[0].similarity_score, 0.4)

    def test_summarize_pr(self):
        req = PRSummaryRequest(
            number=42,
            title="feat(auth): add OAuth2 refresh token rotation",
            body="Implements refresh token rotation to enhance session security.",
            author="alice",
            files=[
                PRFileItem(filename="app/auth/tokens.py", status="modified", additions=45, deletions=5),
                PRFileItem(filename="app/config.py", status="modified", additions=10, deletions=2),
            ],
        )
        res = summarize_pull_request(req)
        self.assertEqual(res.number, 42)
        self.assertTrue(len(res.key_changes) > 0)
        self.assertIn(res.risk_level, ["medium", "high"])

    def test_audit_missing_tests_and_docs(self):
        req = PRAuditRequest(
            number=99,
            title="Add payment gateway webhook handler",
            body="New endpoint for stripe webhooks.",
            files=[
                PRFileItem(filename="backend/app/payments.py", status="added", additions=120, deletions=0),
                PRFileItem(filename="backend/app/config.py", status="modified", additions=8, deletions=1),
            ],
        )
        res = audit_pull_request(req)
        self.assertIn(res.readiness, ["Needs Tests", "Needs Tests & Docs"])
        self.assertEqual(res.test_status, "missing")
        self.assertTrue(len(res.suggested_test_scaffold) > 0)

    def test_generate_release_notes(self):
        prs = [
            ClosedPRItem(number=1, title="feat: add dark mode theme toggle", author="dev1", labels=["enhancement"]),
            ClosedPRItem(number=2, title="fix: resolve memory leak in websocket listener", author="dev2", labels=["bug"]),
            ClosedPRItem(number=3, title="docs: update API authentication guide", author="writer1", labels=["documentation"]),
        ]
        req = ReleaseNotesRequest(
            owner="acme",
            repo="awesome-project",
            current_version="v1.2.0",
            pull_requests=prs,
        )
        res = generate_release_notes(req)
        self.assertEqual(res.bump_type, "minor")
        self.assertEqual(res.recommended_version, "v1.3.0")
        self.assertEqual(len(res.features), 1)
        self.assertEqual(len(res.bug_fixes), 1)
        self.assertEqual(len(res.documentation), 1)
        self.assertIn("dev1", res.contributors)
        self.assertIn("# Release v1.3.0", res.markdown)


if __name__ == "__main__":
    unittest.main()
