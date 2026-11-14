from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from app.config import settings
from app.schemas import (
    TriageRequest,
    DuplicateDetectRequest,
    PRSummaryRequest,
    PRAuditRequest,
    ReleaseNotesRequest,
    WebhookResponse,
)
from app.services.github import (
    list_issues,
    list_pull_requests,
    get_pull_request_files,
    list_merged_pull_requests,
    verify_webhook_signature,
)
from app.services.triage import analyze_issue
from app.services.duplicate import detect_duplicates
from app.services.pr_summary import summarize_pull_request
from app.services.audit import audit_pull_request
from app.services.release_notes import generate_release_notes
from app.services.webhooks import process_github_webhook

app = FastAPI(
    title="OSS Maintainer Copilot API",
    version="1.0.0",
    description="GitHub Copilot App for Open-Source Maintainers: issue triage, duplicate detection, PR summarization, test/docs audit, and release notes.",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "oss-maintainer-copilot",
        "features": [
            "issue_categorization",
            "duplicate_detection",
            "pr_summarization",
            "test_and_docs_audit",
            "release_notes_generator",
            "github_app_webhooks",
        ],
        "has_openai_key": bool(settings.openai_api_key),
        "has_github_token": bool(settings.github_token),
    }


# -------------------------------------------------------------
# GitHub Proxy Endpoints
# -------------------------------------------------------------
@app.get("/api/repos/{owner}/{repo}/issues")
async def get_repository_issues(
    owner: str, repo: str, state: str = "open", per_page: int = 30
):
    return await list_issues(owner, repo, state, per_page)


@app.get("/api/repos/{owner}/{repo}/pulls")
async def get_repository_pulls(
    owner: str, repo: str, state: str = "open", per_page: int = 30
):
    return await list_pull_requests(owner, repo, state, per_page)


@app.get("/api/repos/{owner}/{repo}/pulls/{pull_number}/files")
async def get_pr_files(owner: str, repo: str, pull_number: int):
    return await get_pull_request_files(owner, repo, pull_number)


@app.get("/api/repos/{owner}/{repo}/merged-prs")
async def get_merged_prs(owner: str, repo: str, per_page: int = 40):
    return await list_merged_pull_requests(owner, repo, per_page)


# -------------------------------------------------------------
# 1. Categorize GitHub Issues Automatically
# -------------------------------------------------------------
@app.post("/api/triage")
async def triage_issue(payload: TriageRequest):
    try:
        return analyze_issue(payload).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Issue analysis failed: {str(exc)}")


# -------------------------------------------------------------
# 2. Detect Possible Duplicate Issues
# -------------------------------------------------------------
@app.post("/api/duplicates")
async def check_duplicates(payload: DuplicateDetectRequest):
    try:
        return detect_duplicates(payload).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Duplicate check failed: {str(exc)}")


# -------------------------------------------------------------
# 3. Summarize Pull Requests
# -------------------------------------------------------------
@app.post("/api/summarize-pr")
async def summarize_pr(payload: PRSummaryRequest):
    try:
        return summarize_pull_request(payload).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PR summarization failed: {str(exc)}")


# -------------------------------------------------------------
# 4. Identify Missing Tests and Documentation
# -------------------------------------------------------------
@app.post("/api/audit-pr")
async def audit_pr(payload: PRAuditRequest):
    try:
        return audit_pull_request(payload).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PR audit failed: {str(exc)}")


# -------------------------------------------------------------
# 5. Generate Release Notes
# -------------------------------------------------------------
@app.post("/api/release-notes")
async def create_release_notes(payload: ReleaseNotesRequest):
    try:
        return generate_release_notes(payload).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Release notes generation failed: {str(exc)}")


# -------------------------------------------------------------
# 6. GitHub App Webhook Receiver
# -------------------------------------------------------------
@app.post("/api/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
):
    body_bytes = await request.body()

    # Validate HMAC signature if secret is configured
    if settings.github_webhook_secret:
        if not verify_webhook_signature(body_bytes, x_hub_signature_256, settings.github_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")

    if not x_github_event:
        raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")

    payload = await request.json()
    response = await process_github_webhook(x_github_event, payload)
    return response.model_dump()
