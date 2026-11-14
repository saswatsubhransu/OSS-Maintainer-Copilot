from typing import Dict, Any, Optional
from app.schemas import (
    WebhookResponse,
    TriageRequest,
    DuplicateDetectRequest,
    IssueItem,
    PRSummaryRequest,
    PRAuditRequest,
    PRFileItem,
)
from app.services.triage import analyze_issue
from app.services.duplicate import detect_duplicates
from app.services.pr_summary import summarize_pull_request
from app.services.audit import audit_pull_request


async def process_github_webhook(event: str, payload: Dict[str, Any]) -> WebhookResponse:
    action = payload.get("action")

    # 1. Handle new issues
    if event == "issues" and action in ["opened", "reopened"]:
        issue_data = payload.get("issue", {})
        title = issue_data.get("title", "")
        body = issue_data.get("body", "") or ""
        labels = [l.get("name") for l in issue_data.get("labels", [])]

        # Auto-triage
        triage_req = TriageRequest(title=title, body=body, labels=labels)
        triage_res = analyze_issue(triage_req)

        return WebhookResponse(
            event=event,
            action=action,
            handled=True,
            summary=f"Auto-triaged Issue #{issue_data.get('number')}: category='{triage_res.category}', priority='{triage_res.priority}'",
            data={
                "issue_number": issue_data.get("number"),
                "triage": triage_res.model_dump(),
            },
        )

    # 2. Handle Pull Requests
    if event == "pull_request" and action in ["opened", "synchronize", "reopened"]:
        pr_data = payload.get("pull_request", {})
        title = pr_data.get("title", "")
        body = pr_data.get("body", "") or ""
        author = pr_data.get("user", {}).get("login", "contributor")
        number = pr_data.get("number", 0)

        # Convert files if present in webhook payload or mock
        summary_req = PRSummaryRequest(
            number=number,
            title=title,
            body=body,
            author=author,
            files=[],
        )
        summary_res = summarize_pull_request(summary_req)

        audit_req = PRAuditRequest(
            number=number,
            title=title,
            body=body,
            files=[],
        )
        audit_res = audit_pull_request(audit_req)

        return WebhookResponse(
            event=event,
            action=action,
            handled=True,
            summary=f"Processed PR #{number}: risk='{summary_res.risk_level}', readiness='{audit_res.readiness}'",
            data={
                "pr_number": number,
                "summary": summary_res.model_dump(),
                "audit": audit_res.model_dump(),
            },
        )

    return WebhookResponse(
        event=event,
        action=action,
        handled=False,
        summary=f"Ignored unsupported event '{event}' with action '{action}'.",
        data=None,
    )
