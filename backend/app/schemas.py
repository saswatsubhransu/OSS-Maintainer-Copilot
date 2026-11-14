from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


# -------------------------------------------------------------
# 1. Issue Categorization & Triage
# -------------------------------------------------------------
class TriageRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=20000)
    labels: List[str] = Field(default_factory=list)


class TriageResult(BaseModel):
    category: str  # bug, feature_request, documentation, performance, security, question, maintenance, other
    priority: str  # low, medium, high, urgent
    suggested_labels: List[str] = Field(default_factory=list)
    component: str = "general"
    summary: str
    next_steps: List[str] = Field(default_factory=list)
    confidence: str = "medium"  # low, medium, high
    caveats: List[str] = Field(default_factory=list)
    draft_response: str = ""


# -------------------------------------------------------------
# 2. Duplicate Detection
# -------------------------------------------------------------
class IssueItem(BaseModel):
    number: int
    title: str
    body: Optional[str] = ""
    html_url: Optional[str] = ""
    state: Optional[str] = "open"
    labels: List[str] = Field(default_factory=list)


class DuplicateDetectRequest(BaseModel):
    target_issue: IssueItem
    candidate_issues: List[IssueItem] = Field(default_factory=list)
    threshold: float = Field(default=0.35, ge=0.0, le=1.0)


class DuplicateMatch(BaseModel):
    issue_number: int
    title: str
    html_url: str
    state: str
    similarity_score: float  # 0.0 to 1.0 (e.g. 0.82 = 82%)
    confidence: str  # low, medium, high
    matching_signals: List[str] = Field(default_factory=list)
    distinctions: List[str] = Field(default_factory=list)
    recommendation: str  # e.g., "Potential duplicate - inspect comments", "Close as duplicate of #..."


class DuplicateDetectResult(BaseModel):
    has_duplicates: bool
    top_matches: List[DuplicateMatch] = Field(default_factory=list)
    analysis_summary: str


# -------------------------------------------------------------
# 3. Pull Request Summarizer
# -------------------------------------------------------------
class PRFileItem(BaseModel):
    filename: str
    status: Optional[str] = "modified"  # added, modified, removed
    additions: int = 0
    deletions: int = 0
    patch: Optional[str] = None


class PRSummaryRequest(BaseModel):
    number: int
    title: str
    body: Optional[str] = ""
    author: Optional[str] = "contributor"
    diff_summary: Optional[str] = ""
    files: List[PRFileItem] = Field(default_factory=list)


class PRSummaryResult(BaseModel):
    number: int
    title: str
    tldr: str
    key_changes: List[str] = Field(default_factory=list)
    architectural_impact: str
    breaking_changes: List[str] = Field(default_factory=list)
    risk_level: str  # low, medium, high
    risk_reasons: List[str] = Field(default_factory=list)
    review_checklist: List[str] = Field(default_factory=list)
    markdown_summary: str = ""


# -------------------------------------------------------------
# 4. Missing Tests & Documentation Auditor
# -------------------------------------------------------------
class PRAuditRequest(BaseModel):
    number: int
    title: str
    body: Optional[str] = ""
    files: List[PRFileItem] = Field(default_factory=list)


class PRAuditResult(BaseModel):
    number: int
    readiness: str  # "Ready for Review", "Needs Tests", "Needs Docs", "Needs Tests & Docs"
    test_status: str  # "ok", "warning", "missing"
    docs_status: str  # "ok", "warning", "missing"
    test_findings: List[str] = Field(default_factory=list)
    docs_findings: List[str] = Field(default_factory=list)
    suggested_test_scaffold: str = ""
    suggested_doc_snippet: str = ""
    recommended_action: str = ""


# -------------------------------------------------------------
# 5. Release Notes Generator
# -------------------------------------------------------------
class ClosedPRItem(BaseModel):
    number: int
    title: str
    body: Optional[str] = ""
    author: Optional[str] = "contributor"
    labels: List[str] = Field(default_factory=list)
    merged_at: Optional[str] = None


class ReleaseNotesRequest(BaseModel):
    owner: str
    repo: str
    current_version: Optional[str] = "v0.1.0"
    target_version: Optional[str] = None
    pull_requests: List[ClosedPRItem] = Field(default_factory=list)


class ReleaseNoteEntry(BaseModel):
    title: str
    number: int
    author: str
    category: str  # feature, fix, breaking, docs, chore


class ReleaseNotesResult(BaseModel):
    recommended_version: str
    bump_type: str  # major, minor, patch
    bump_reason: str
    features: List[ReleaseNoteEntry] = Field(default_factory=list)
    bug_fixes: List[ReleaseNoteEntry] = Field(default_factory=list)
    breaking_changes: List[ReleaseNoteEntry] = Field(default_factory=list)
    documentation: List[ReleaseNoteEntry] = Field(default_factory=list)
    maintenance: List[ReleaseNoteEntry] = Field(default_factory=list)
    contributors: List[str] = Field(default_factory=list)
    markdown: str


# -------------------------------------------------------------
# 6. GitHub Webhook Payload Models
# -------------------------------------------------------------
class WebhookResponse(BaseModel):
    event: str
    action: Optional[str] = None
    handled: bool
    summary: str
    data: Optional[Dict[str, Any]] = None
