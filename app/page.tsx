"use client";

import { useState, useEffect } from "react";

// Types
type Issue = {
  number: number;
  title: string;
  body: string | null;
  html_url: string;
  state: string;
  labels: string[];
  is_pull_request: boolean;
  author?: string;
  comments_count?: number;
};

type PullRequest = {
  number: number;
  title: string;
  body: string | null;
  html_url: string;
  state: string;
  author: string;
  labels: string[];
  draft: boolean;
  merged_at: string | null;
  head_ref: string;
  base_ref: string;
};

type PRFile = {
  filename: string;
  status: string;
  additions: number;
  deletions: number;
  changes: number;
  patch?: string;
};

type TriageResult = {
  category: string;
  priority: string;
  suggested_labels: string[];
  component: string;
  summary: string;
  next_steps: string[];
  confidence: string;
  caveats: string[];
  draft_response: string;
};

type DuplicateMatch = {
  issue_number: number;
  title: string;
  html_url: string;
  state: string;
  similarity_score: number;
  confidence: string;
  matching_signals: string[];
  distinctions: string[];
  recommendation: string;
};

type DuplicateResult = {
  has_duplicates: boolean;
  top_matches: DuplicateMatch[];
  analysis_summary: string;
};

type PRSummaryResult = {
  number: number;
  title: string;
  tldr: string;
  key_changes: string[];
  architectural_impact: string;
  breaking_changes: string[];
  risk_level: string;
  risk_reasons: string[];
  review_checklist: string[];
  markdown_summary: string;
};

type PRAuditResult = {
  number: number;
  readiness: string;
  test_status: string;
  docs_status: string;
  test_findings: string[];
  docs_findings: string[];
  suggested_test_scaffold: string;
  suggested_doc_snippet: string;
  recommended_action: string;
};

type ReleaseNoteEntry = {
  title: string;
  number: number;
  author: string;
  category: string;
};

type ReleaseNotesResult = {
  recommended_version: string;
  bump_type: string;
  bump_reason: string;
  features: ReleaseNoteEntry[];
  bug_fixes: ReleaseNoteEntry[];
  breaking_changes: ReleaseNoteEntry[];
  documentation: ReleaseNoteEntry[];
  maintenance: ReleaseNoteEntry[];
  contributors: string[];
  markdown: string;
};

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const PRESET_REPOS = [
  "fastapi/fastapi",
  "pallets/flask",
  "tiangolo/sqlmodel",
  "encode/httpx",
  "vercel/next.js",
];

export default function Home() {
  const [repo, setRepo] = useState("fastapi/fastapi");
  const [activeTab, setActiveTab] = useState<
    "triage" | "duplicates" | "pr_summary" | "pr_audit" | "release_notes" | "webhook_guide"
  >("triage");

  // Repository Data
  const [issues, setIssues] = useState<Issue[]>([]);
  const [pulls, setPulls] = useState<PullRequest[]>([]);
  const [mergedPRs, setMergedPRs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copiedText, setCopiedText] = useState("");

  // Tab 1: Triage State
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [triageResult, setTriageResult] = useState<TriageResult | null>(null);

  // Tab 2: Duplicate State
  const [dupTargetIssue, setDupTargetIssue] = useState<Issue | null>(null);
  const [customDupTitle, setCustomDupTitle] = useState("");
  const [customDupBody, setCustomDupBody] = useState("");
  const [dupResult, setDupResult] = useState<DuplicateResult | null>(null);

  // Tab 3: PR Summary State
  const [selectedPR, setSelectedPR] = useState<PullRequest | null>(null);
  const [prFiles, setPrFiles] = useState<PRFile[]>([]);
  const [prSummaryResult, setPrSummaryResult] = useState<PRSummaryResult | null>(null);

  // Tab 4: PR Audit State
  const [prAuditResult, setPrAuditResult] = useState<PRAuditResult | null>(null);

  // Tab 5: Release Notes State
  const [currentVersion, setCurrentVersion] = useState("v1.2.0");
  const [releaseNotesResult, setReleaseNotesResult] = useState<ReleaseNotesResult | null>(null);

  // Tab 6: Webhook Simulator State
  const [simEventType, setSimEventType] = useState("issues");
  const [simResponse, setSimResponse] = useState<any>(null);

  function copyToClipboard(text: string, label: string) {
    navigator.clipboard.writeText(text);
    setCopiedText(label);
    setTimeout(() => setCopiedText(""), 2000);
  }

  // Load Repo Issues & PRs
  async function loadRepoData(targetRepo = repo) {
    const parts = targetRepo.trim().split("/");
    if (parts.length !== 2 || !parts[0] || !parts[1]) {
      setError("Please enter repository in owner/repo format (e.g. fastapi/fastapi)");
      return;
    }
    setLoading(true);
    setError("");
    setSelectedIssue(null);
    setTriageResult(null);
    setDupResult(null);
    setSelectedPR(null);
    setPrSummaryResult(null);
    setPrAuditResult(null);
    setReleaseNotesResult(null);

    const owner = encodeURIComponent(parts[0]);
    const repoName = encodeURIComponent(parts[1]);

    try {
      // 1. Fetch Issues
      const issuesRes = await fetch(`${API}/api/repos/${owner}/${repoName}/issues?state=open&per_page=30`);
      if (!issuesRes.ok) {
        const errData = await issuesRes.json();
        throw new Error(errData.detail || "Failed to load issues");
      }
      const issuesData = await issuesRes.json();
      setIssues(issuesData.filter((i: Issue) => !i.is_pull_request));

      // 2. Fetch PRs
      const pullsRes = await fetch(`${API}/api/repos/${owner}/${repoName}/pulls?state=open&per_page=25`);
      if (pullsRes.ok) {
        const pullsData = await pullsRes.json();
        setPulls(pullsData);
      }

      // 3. Fetch Merged PRs
      const mergedRes = await fetch(`${API}/api/repos/${owner}/${repoName}/merged-prs?per_page=30`);
      if (mergedRes.ok) {
        const mergedData = await mergedRes.json();
        setMergedPRs(mergedData);
      }
    } catch (err: any) {
      setError(err.message || "Failed to fetch repository information");
    } finally {
      setLoading(false);
    }
  }

  // Action 1: Triage Issue
  async function analyzeTriage(issue: Issue) {
    setSelectedIssue(issue);
    setTriageResult(null);
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API}/api/triage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: issue.title,
          body: issue.body || "",
          labels: issue.labels,
        }),
      });
      if (!res.ok) throw new Error("Triage analysis failed");
      const data = await res.json();
      setTriageResult(data);
    } catch (err: any) {
      setError(err.message || "Triage failed");
    } finally {
      setLoading(false);
    }
  }

  // Action 2: Detect Duplicates
  async function runDuplicateDetection(target: Issue | { number: number; title: string; body: string }) {
    setLoading(true);
    setError("");
    setDupResult(null);
    try {
      const candidateIssues = issues.map((i) => ({
        number: i.number,
        title: i.title,
        body: i.body || "",
        html_url: i.html_url,
        state: i.state,
        labels: i.labels,
      }));

      const res = await fetch(`${API}/api/duplicates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_issue: {
            number: target.number,
            title: target.title,
            body: target.body || "",
          },
          candidate_issues: candidateIssues,
          threshold: 0.25,
        }),
      });
      if (!res.ok) throw new Error("Duplicate detection failed");
      const data = await res.json();
      setDupResult(data);
    } catch (err: any) {
      setError(err.message || "Duplicate check failed");
    } finally {
      setLoading(false);
    }
  }

  // Action 3: Summarize PR
  async function handleSummarizePR(pr: PullRequest) {
    setSelectedPR(pr);
    setPrSummaryResult(null);
    setLoading(true);
    setError("");
    try {
      const parts = repo.split("/");
      const filesRes = await fetch(`${API}/api/repos/${parts[0]}/${parts[1]}/pulls/${pr.number}/files`);
      const files: PRFile[] = filesRes.ok ? await filesRes.json() : [];
      setPrFiles(files);

      const res = await fetch(`${API}/api/summarize-pr`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          number: pr.number,
          title: pr.title,
          body: pr.body || "",
          author: pr.author,
          files: files,
        }),
      });
      if (!res.ok) throw new Error("PR summary failed");
      const data = await res.json();
      setPrSummaryResult(data);
    } catch (err: any) {
      setError(err.message || "PR summarization failed");
    } finally {
      setLoading(false);
    }
  }

  // Action 4: Audit Missing Tests and Documentation
  async function handleAuditPR(pr: PullRequest) {
    setSelectedPR(pr);
    setPrAuditResult(null);
    setLoading(true);
    setError("");
    try {
      const parts = repo.split("/");
      let files = prFiles;
      if (!files.length) {
        const filesRes = await fetch(`${API}/api/repos/${parts[0]}/${parts[1]}/pulls/${pr.number}/files`);
        files = filesRes.ok ? await filesRes.json() : [];
        setPrFiles(files);
      }

      const res = await fetch(`${API}/api/audit-pr`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          number: pr.number,
          title: pr.title,
          body: pr.body || "",
          files: files,
        }),
      });
      if (!res.ok) throw new Error("PR audit failed");
      const data = await res.json();
      setPrAuditResult(data);
    } catch (err: any) {
      setError(err.message || "Audit failed");
    } finally {
      setLoading(false);
    }
  }

  // Action 5: Generate Release Notes
  async function handleGenerateReleaseNotes() {
    setLoading(true);
    setError("");
    setReleaseNotesResult(null);
    try {
      const parts = repo.split("/");
      const res = await fetch(`${API}/api/release-notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          owner: parts[0],
          repo: parts[1],
          current_version: currentVersion,
          pull_requests: mergedPRs.length ? mergedPRs : pulls,
        }),
      });
      if (!res.ok) throw new Error("Failed to generate release notes");
      const data = await res.json();
      setReleaseNotesResult(data);
    } catch (err: any) {
      setError(err.message || "Release notes generation failed");
    } finally {
      setLoading(false);
    }
  }

  // Action 6: Simulate Webhook
  async function handleSimulateWebhook() {
    setLoading(true);
    setError("");
    setSimResponse(null);
    try {
      let payload = {};
      if (simEventType === "issues") {
        payload = {
          action: "opened",
          issue: {
            number: 999,
            title: "Crash on booting auth middleware with invalid token",
            body: "Null pointer exception encountered in token validation parser.\n```\nTraceback...\n```",
            labels: [{ name: "bug" }],
          },
        };
      } else {
        payload = {
          action: "opened",
          pull_request: {
            number: 1001,
            title: "feat(auth): add rate limiting and session refresh token support",
            body: "This PR implements security enhancements for token expiry.",
            user: { login: "contributor_octocat" },
          },
        };
      }

      const res = await fetch(`${API}/api/webhooks/github`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-GitHub-Event": simEventType,
        },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      setSimResponse(data);
    } catch (err: any) {
      setError(err.message || "Webhook test failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell">
      {/* Topbar */}
      <header className="topbar">
        <div className="brand-mark">OC</div>
        <div>
          <div className="brand">OSS Maintainer Copilot</div>
          <div className="muted small">Autonomous intelligence for GitHub maintainers & open-source projects</div>
        </div>
        <div className="topbar-actions">
          <span className="status">● All 5 Copilot Engines Active</span>
        </div>
      </header>

      {/* Hero Section */}
      <section className="hero">
        <p className="eyebrow">OPEN SOURCE MAINTAINER PLATFORM</p>
        <h1>
          Maintain with velocity.<br />
          <span>Keep human maintainers in control.</span>
        </h1>
        <p className="intro">
          Automate triage categorization, detect duplicate issues, generate pull request summaries,
          audit missing tests & documentation, and build release notes with one click.
        </p>
      </section>

      {/* Repo Selector Card */}
      <section className="repo-card">
        <div className="repo-header-row">
          <label htmlFor="repo">Active GitHub Repository</label>
          <div className="preset-group">
            <span className="muted small">Quick try:</span>
            {PRESET_REPOS.map((p) => (
              <button
                key={p}
                className="pill-btn"
                onClick={() => {
                  setRepo(p);
                  loadRepoData(p);
                }}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
        <div className="repo-row">
          <input
            id="repo"
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            placeholder="owner/repository (e.g. fastapi/fastapi)"
          />
          <button onClick={() => loadRepoData()} disabled={loading}>
            {loading ? "Loading…" : "Load Repository"}
          </button>
        </div>
      </section>

      {error && (
        <div className="error" role="alert">
          <strong>Notice:</strong> {error}
        </div>
      )}

      {/* Navigation Tabs */}
      <nav className="tab-bar">
        <button
          className={`tab-btn ${activeTab === "triage" ? "active" : ""}`}
          onClick={() => setActiveTab("triage")}
        >
          🏷️ 1. Issue Categorizer
          {issues.length > 0 && <span className="tab-badge">{issues.length}</span>}
        </button>
        <button
          className={`tab-btn ${activeTab === "duplicates" ? "active" : ""}`}
          onClick={() => setActiveTab("duplicates")}
        >
          🔍 2. Duplicate Detector
        </button>
        <button
          className={`tab-btn ${activeTab === "pr_summary" ? "active" : ""}`}
          onClick={() => setActiveTab("pr_summary")}
        >
          🔀 3. PR Summarizer
          {pulls.length > 0 && <span className="tab-badge">{pulls.length}</span>}
        </button>
        <button
          className={`tab-btn ${activeTab === "pr_audit" ? "active" : ""}`}
          onClick={() => setActiveTab("pr_audit")}
        >
          🧪 4. Missing Tests & Docs Auditor
        </button>
        <button
          className={`tab-btn ${activeTab === "release_notes" ? "active" : ""}`}
          onClick={() => setActiveTab("release_notes")}
        >
          📦 5. Release Notes
          {mergedPRs.length > 0 && <span className="tab-badge">{mergedPRs.length}</span>}
        </button>
        <button
          className={`tab-btn ${activeTab === "webhook_guide" ? "active" : ""}`}
          onClick={() => setActiveTab("webhook_guide")}
        >
          ⚡ GitHub App Webhooks
        </button>
      </nav>

      {/* TAB 1: Issue Categorizer */}
      {activeTab === "triage" && (
        <div className="workspace">
          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">INCOMING ISSUES</p>
                <h2>Open Issues</h2>
              </div>
              <span className="count">{issues.length}</span>
            </div>
            {issues.length === 0 ? (
              <div className="empty">
                No issues loaded. Click &ldquo;Load Repository&rdquo; above to fetch live issues.
              </div>
            ) : (
              <div className="issue-list">
                {issues.map((issue) => (
                  <button
                    key={issue.number}
                    className={`issue ${selectedIssue?.number === issue.number ? "selected" : ""}`}
                    onClick={() => analyzeTriage(issue)}
                  >
                    <div className="issue-topline">
                      <span className="issue-number">#{issue.number}</span>
                      <span className="muted small">@{issue.author || "user"}</span>
                    </div>
                    <strong>{issue.title}</strong>
                    <div className="label-row">
                      {issue.labels.length > 0 ? (
                        issue.labels.map((l) => (
                          <span key={l} className="label-tag">
                            {l}
                          </span>
                        ))
                      ) : (
                        <span className="muted small">No labels</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="panel detail">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">AI CATEGORIZATION & TRIAGE</p>
                <h2>{selectedIssue ? `Issue #${selectedIssue.number}` : "Select an Issue"}</h2>
              </div>
              {triageResult && (
                <button
                  className="copy-btn"
                  onClick={() =>
                    copyToClipboard(triageResult.draft_response, "Draft Comment")
                  }
                >
                  {copiedText === "Draft Comment" ? "✓ Copied Comment" : "📋 Copy Maintainer Reply"}
                </button>
              )}
            </div>

            {!selectedIssue && (
              <div className="empty">
                Click on any issue from the left panel to trigger automatic categorization, priority
                scoring, suggested labels, and maintainer next steps.
              </div>
            )}

            {selectedIssue && <p className="issue-headline">{selectedIssue.title}</p>}

            {loading && <div className="loading-spinner">Analyzing issue content & patterns…</div>}

            {triageResult && (
              <div className="analysis-box">
                <div className="chips">
                  <span className={`chip-badge category-${triageResult.category}`}>
                    🏷️ {triageResult.category.toUpperCase().replace("_", " ")}
                  </span>
                  <span className={`chip-badge priority-${triageResult.priority}`}>
                    ⚡ Priority: {triageResult.priority.toUpperCase()}
                  </span>
                  <span className="chip-badge component-tag">
                    📦 Component: {triageResult.component}
                  </span>
                  <span className="chip-badge">
                    Confidence: {triageResult.confidence}
                  </span>
                </div>

                <h3>Suggested Standard Labels</h3>
                <div className="label-row">
                  {triageResult.suggested_labels.map((lbl) => (
                    <span key={lbl} className="suggested-label">
                      +{lbl}
                    </span>
                  ))}
                  <button
                    className="small-btn"
                    onClick={() =>
                      copyToClipboard(
                        triageResult.suggested_labels.join(", "),
                        "Labels"
                      )
                    }
                  >
                    {copiedText === "Labels" ? "✓ Copied" : "Copy Labels"}
                  </button>
                </div>

                <h3>Executive Summary</h3>
                <p className="summary-text">{triageResult.summary}</p>

                <h3>Actionable Next Steps for Maintainers</h3>
                <ul className="step-list">
                  {triageResult.next_steps.map((s, idx) => (
                    <li key={idx}>{s}</li>
                  ))}
                </ul>

                {triageResult.caveats.length > 0 && (
                  <div className="warning-box">
                    <h4>⚠️ Missing Information / Caveats</h4>
                    <ul>
                      {triageResult.caveats.map((c, idx) => (
                        <li key={idx}>{c}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <h3>Ready-to-Post Maintainer Reply Draft</h3>
                <div className="code-card">
                  <pre>{triageResult.draft_response}</pre>
                </div>

                <a
                  className="external"
                  href={selectedIssue?.html_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  View original issue on GitHub ↗
                </a>
              </div>
            )}
          </section>
        </div>
      )}

      {/* TAB 2: Duplicate Issue Detector */}
      {activeTab === "duplicates" && (
        <div className="workspace">
          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">TARGET SELECTION</p>
                <h2>Detect Possible Duplicates</h2>
              </div>
            </div>

            <p className="muted small">
              Select an existing open issue or type a title below to scan for semantic and technical duplicates.
            </p>

            <div className="custom-input-box">
              <label>Custom Issue Title to Test</label>
              <input
                value={customDupTitle}
                onChange={(e) => setCustomDupTitle(e.target.value)}
                placeholder="e.g. Memory leak during long-lived websocket connections"
              />
              <button
                className="run-btn"
                onClick={() =>
                  runDuplicateDetection({
                    number: 0,
                    title: customDupTitle || "Custom Bug",
                    body: customDupBody,
                  })
                }
                disabled={loading || !customDupTitle}
              >
                Scan Repository For Duplicates
              </button>
            </div>

            <div className="separator">OR SELECT AN EXISTING ISSUE</div>

            <div className="issue-list">
              {issues.map((issue) => (
                <button
                  key={issue.number}
                  className={`issue ${dupTargetIssue?.number === issue.number ? "selected" : ""}`}
                  onClick={() => {
                    setDupTargetIssue(issue);
                    runDuplicateDetection(issue);
                  }}
                >
                  <span className="issue-number">#{issue.number}</span>
                  <strong>{issue.title}</strong>
                </button>
              ))}
            </div>
          </section>

          <section className="panel detail">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">SIMILARITY RADAR</p>
                <h2>Duplicate Detection Results</h2>
              </div>
            </div>

            {!dupResult && !loading && (
              <div className="empty">
                Select an issue on the left or enter a custom title to find matching issues and duplicate bug reports.
              </div>
            )}

            {loading && <div className="loading-spinner">Scanning repository issues for duplicate signatures…</div>}

            {dupResult && (
              <div>
                <div
                  className={`status-banner ${
                    dupResult.has_duplicates ? "banner-warning" : "banner-success"
                  }`}
                >
                  <strong>{dupResult.has_duplicates ? "⚠️ Duplicates Detected" : "✓ No Severe Duplicates"}</strong>
                  <p>{dupResult.analysis_summary}</p>
                </div>

                <div className="match-list">
                  {dupResult.top_matches.map((match) => (
                    <div key={match.issue_number} className="match-card">
                      <div className="match-header">
                        <div>
                          <span className="issue-number">#{match.issue_number}</span>
                          <strong className="match-title">{match.title}</strong>
                        </div>
                        <span className="score-badge">
                          {Math.round(match.similarity_score * 100)}% Match
                        </span>
                      </div>

                      <div className="match-body">
                        <div className="signal-section">
                          <p className="eyebrow">MATCHING SIGNALS</p>
                          <ul>
                            {match.matching_signals.map((sig, i) => (
                              <li key={i}>{sig}</li>
                            ))}
                          </ul>
                        </div>

                        {match.distinctions.length > 0 && (
                          <div className="signal-section">
                            <p className="eyebrow">DIFFERENCES</p>
                            <ul>
                              {match.distinctions.map((d, i) => (
                                <li key={i}>{d}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        <div className="rec-box">
                          <strong>Copilot Recommendation:</strong> {match.recommendation}
                        </div>

                        <a
                          href={match.html_url}
                          target="_blank"
                          rel="noreferrer"
                          className="external small"
                        >
                          Inspect #{match.issue_number} on GitHub ↗
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {/* TAB 3: PR Summarizer */}
      {activeTab === "pr_summary" && (
        <div className="workspace">
          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">PULL REQUESTS</p>
                <h2>Open Pull Requests</h2>
              </div>
              <span className="count">{pulls.length}</span>
            </div>
            {pulls.length === 0 ? (
              <div className="empty">No open pull requests found. Try loading another repository.</div>
            ) : (
              <div className="issue-list">
                {pulls.map((pr) => (
                  <button
                    key={pr.number}
                    className={`issue ${selectedPR?.number === pr.number ? "selected" : ""}`}
                    onClick={() => handleSummarizePR(pr)}
                  >
                    <div className="issue-topline">
                      <span className="issue-number">PR #{pr.number}</span>
                      <span className="muted small">by @{pr.author}</span>
                    </div>
                    <strong>{pr.title}</strong>
                    <span className="muted small">{pr.base_ref} ← {pr.head_ref}</span>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="panel detail">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">AI PR BREAKDOWN</p>
                <h2>{selectedPR ? `PR #${selectedPR.number} Summary` : "Select a Pull Request"}</h2>
              </div>
              {prSummaryResult && (
                <button
                  className="copy-btn"
                  onClick={() =>
                    copyToClipboard(prSummaryResult.markdown_summary, "PR Summary")
                  }
                >
                  {copiedText === "PR Summary" ? "✓ Copied" : "📋 Copy Markdown"}
                </button>
              )}
            </div>

            {!selectedPR && (
              <div className="empty">
                Select a pull request to generate an executive TL;DR, changed files breakdown, architectural impact,
                breaking change alerts, and reviewer checklist.
              </div>
            )}

            {selectedPR && <p className="issue-headline">{selectedPR.title}</p>}

            {loading && <div className="loading-spinner">Analyzing pull request diff & commits…</div>}

            {prSummaryResult && (
              <div className="analysis-box">
                <div className="chips">
                  <span className={`chip-badge risk-${prSummaryResult.risk_level}`}>
                    Risk: {prSummaryResult.risk_level.toUpperCase()}
                  </span>
                  <span className="chip-badge">{prFiles.length} Changed Files</span>
                </div>

                <div className="tldr-box">
                  <strong>TL;DR</strong>
                  <p>{prSummaryResult.tldr}</p>
                </div>

                {prSummaryResult.breaking_changes.length > 0 && (
                  <div className="warning-box">
                    <h4>⚠️ Breaking Changes Detected</h4>
                    <ul>
                      {prSummaryResult.breaking_changes.map((b, i) => (
                        <li key={i}>{b}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <h3>Key Changes Breakdown</h3>
                <ul className="step-list">
                  {prSummaryResult.key_changes.map((kc, i) => (
                    <li key={i}>{kc}</li>
                  ))}
                </ul>

                <h3>Architectural Impact</h3>
                <p className="summary-text">{prSummaryResult.architectural_impact}</p>

                <h3>Maintainer Review Checklist</h3>
                <ul className="step-list">
                  {prSummaryResult.review_checklist.map((chk, i) => (
                    <li key={i}>{chk}</li>
                  ))}
                </ul>

                <a
                  className="external"
                  href={selectedPR?.html_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open PR #{selectedPR?.number} on GitHub ↗
                </a>
              </div>
            )}
          </section>
        </div>
      )}

      {/* TAB 4: Missing Tests and Documentation Auditor */}
      {activeTab === "pr_audit" && (
        <div className="workspace">
          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">QUALITY AUDIT</p>
                <h2>Inspect PR Coverage</h2>
              </div>
            </div>
            <p className="muted small">
              Select a pull request to verify whether new features or bug fixes have corresponding test files
              and documentation updates.
            </p>
            <div className="issue-list">
              {pulls.map((pr) => (
                <button
                  key={pr.number}
                  className={`issue ${selectedPR?.number === pr.number ? "selected" : ""}`}
                  onClick={() => handleAuditPR(pr)}
                >
                  <span className="issue-number">PR #{pr.number}</span>
                  <strong>{pr.title}</strong>
                  <span className="muted small">@{pr.author}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="panel detail">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">AUDIT REPORT</p>
                <h2>{selectedPR ? `PR #${selectedPR.number} Quality Findings` : "Audit Findings"}</h2>
              </div>
            </div>

            {!selectedPR && (
              <div className="empty">
                Select a pull request to audit code files for missing unit tests and documentation snippets.
              </div>
            )}

            {loading && <div className="loading-spinner">Auditing test coverage and documentation updates…</div>}

            {prAuditResult && (
              <div className="analysis-box">
                <div className="chips">
                  <span
                    className={`chip-badge ${
                      prAuditResult.readiness.includes("Ready")
                        ? "banner-success"
                        : "banner-warning"
                    }`}
                  >
                    Readiness: {prAuditResult.readiness}
                  </span>
                  <span className="chip-badge">Tests: {prAuditResult.test_status.toUpperCase()}</span>
                  <span className="chip-badge">Docs: {prAuditResult.docs_status.toUpperCase()}</span>
                </div>

                <h3>🧪 Test Coverage Audit</h3>
                <ul className="step-list">
                  {prAuditResult.test_findings.map((tf, i) => (
                    <li key={i}>{tf}</li>
                  ))}
                </ul>

                <h3>📚 Documentation Audit</h3>
                <ul className="step-list">
                  {prAuditResult.docs_findings.map((df, i) => (
                    <li key={i}>{df}</li>
                  ))}
                </ul>

                <div className="rec-box">
                  <strong>Recommended Action:</strong> {prAuditResult.recommended_action}
                </div>

                {prAuditResult.suggested_test_scaffold && (
                  <div className="scaffold-section">
                    <div className="section-head">
                      <h3>Generated Unit Test Scaffold</h3>
                      <button
                        className="small-btn"
                        onClick={() =>
                          copyToClipboard(prAuditResult.suggested_test_scaffold, "Test Scaffold")
                        }
                      >
                        {copiedText === "Test Scaffold" ? "✓ Copied" : "Copy Test Code"}
                      </button>
                    </div>
                    <div className="code-card">
                      <pre>{prAuditResult.suggested_test_scaffold}</pre>
                    </div>
                  </div>
                )}

                {prAuditResult.suggested_doc_snippet && (
                  <div className="scaffold-section">
                    <div className="section-head">
                      <h3>Generated Documentation Snippet</h3>
                      <button
                        className="small-btn"
                        onClick={() =>
                          copyToClipboard(prAuditResult.suggested_doc_snippet, "Doc Snippet")
                        }
                      >
                        {copiedText === "Doc Snippet" ? "✓ Copied" : "Copy Doc Snippet"}
                      </button>
                    </div>
                    <div className="code-card">
                      <pre>{prAuditResult.suggested_doc_snippet}</pre>
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      )}

      {/* TAB 5: Release Notes Generator */}
      {activeTab === "release_notes" && (
        <div className="workspace">
          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">RELEASE MANAGER</p>
                <h2>Generate Release Notes</h2>
              </div>
              <span className="count">{mergedPRs.length || pulls.length}</span>
            </div>

            <p className="muted small">
              Clusters merged pull requests into standard release categories (Features, Fixes, Breaking Changes,
              Documentation), credits contributors, and calculates SemVer bump.
            </p>

            <div className="custom-input-box">
              <label>Current Release Version</label>
              <input
                value={currentVersion}
                onChange={(e) => setCurrentVersion(e.target.value)}
                placeholder="v1.2.0"
              />
              <button
                className="run-btn"
                onClick={handleGenerateReleaseNotes}
                disabled={loading}
              >
                {loading ? "Generating…" : "Generate Release Notes"}
              </button>
            </div>

            <div className="issue-list">
              {(mergedPRs.length ? mergedPRs : pulls).map((pr) => (
                <div key={pr.number} className="issue">
                  <span className="issue-number">PR #{pr.number}</span>
                  <strong>{pr.title}</strong>
                  <span className="muted small">@{pr.author}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="panel detail">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">CHANGELOG OUTPUT</p>
                <h2>Generated GitHub Release</h2>
              </div>
              {releaseNotesResult && (
                <button
                  className="copy-btn"
                  onClick={() =>
                    copyToClipboard(releaseNotesResult.markdown, "Release Notes")
                  }
                >
                  {copiedText === "Release Notes" ? "✓ Copied" : "📋 Copy GitHub Markdown"}
                </button>
              )}
            </div>

            {!releaseNotesResult && !loading && (
              <div className="empty">
                Click &ldquo;Generate Release Notes&rdquo; to cluster PRs into features, bug fixes, breaking changes, and contributor lists.
              </div>
            )}

            {loading && <div className="loading-spinner">Clustering pull requests and computing semantic bump…</div>}

            {releaseNotesResult && (
              <div className="analysis-box">
                <div className="chips">
                  <span className="chip-badge banner-success">
                    Next Version: {releaseNotesResult.recommended_version}
                  </span>
                  <span className="chip-badge">
                    Bump: {releaseNotesResult.bump_type.toUpperCase()}
                  </span>
                  <span className="chip-badge">
                    {releaseNotesResult.contributors.length} Contributors
                  </span>
                </div>

                <div className="rec-box">
                  <strong>SemVer Justification:</strong> {releaseNotesResult.bump_reason}
                </div>

                <div className="code-card">
                  <pre>{releaseNotesResult.markdown}</pre>
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {/* TAB 6: GitHub App Webhooks Guide & Simulator */}
      {activeTab === "webhook_guide" && (
        <div className="single-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">INTEGRATION & AUTOMATION</p>
              <h2>GitHub App Webhook Integration</h2>
            </div>
          </div>

          <div className="guide-grid">
            <div className="guide-card">
              <h3>1. Register Your GitHub App</h3>
              <p className="muted small">
                Navigate to <strong>GitHub Settings &gt; Developer Settings &gt; GitHub Apps &gt; New GitHub App</strong>.
              </p>
              <ul className="step-list">
                <li><strong>Webhook URL:</strong> <code>https://your-domain.com/api/webhooks/github</code></li>
                <li><strong>Webhook Secret:</strong> Configure matching <code>GITHUB_WEBHOOK_SECRET</code> in backend/.env</li>
                <li><strong>Permissions:</strong> Issues (Read & Write), Pull Requests (Read & Write)</li>
                <li><strong>Subscribe to events:</strong> Issues, Pull requests</li>
              </ul>
            </div>

            <div className="guide-card">
              <h3>2. Interactive Webhook Simulator</h3>
              <p className="muted small">Test webhook processing locally right now without configuring a live GitHub App:</p>
              <div className="repo-row">
                <select
                  value={simEventType}
                  onChange={(e) => setSimEventType(e.target.value)}
                  className="select-input"
                >
                  <option value="issues">Event: issues (action: opened)</option>
                  <option value="pull_request">Event: pull_request (action: opened)</option>
                </select>
                <button onClick={handleSimulateWebhook} disabled={loading}>
                  {loading ? "Simulating…" : "Fire Test Webhook"}
                </button>
              </div>

              {simResponse && (
                <div className="sim-result">
                  <p className="eyebrow">WEBHOOK RECEIVER OUTPUT</p>
                  <div className="code-card">
                    <pre>{JSON.stringify(simResponse, null, 2)}</pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <footer>
        OSS Maintainer Copilot · Built for Open-Source Maintainers · Categorization · Duplicates · PR Summaries · Test/Doc Audits · Release Notes
      </footer>
    </main>
  );
}
