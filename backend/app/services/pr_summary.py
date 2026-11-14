import json
import re
from typing import List, Dict, Any
from openai import OpenAI

from app.config import settings
from app.schemas import PRSummaryRequest, PRSummaryResult, PRFileItem


PR_SUMMARY_PROMPT = """You are an expert open-source maintainer and code reviewer.
Analyze the following Pull Request (including title, description, and modified files/patches) and output ONLY a JSON object:
{
  "tldr": "High-level 1-2 sentence executive summary of what this PR does and why",
  "key_changes": [
    "Short bullet describing change in component X",
    "Short bullet describing change in component Y"
  ],
  "architectural_impact": "Assessment of architectural impact (e.g., state management, API schema, database, none)",
  "breaking_changes": ["List of any backwards-incompatible API, schema, or configuration changes (empty if none)"],
  "risk_level": "low" | "medium" | "high",
  "risk_reasons": ["Reason 1 for this risk level", "Reason 2"],
  "review_checklist": ["Item to verify during review 1", "Item to verify 2"]
}
"""


def _heuristic_pr_summary(pr: PRSummaryRequest) -> PRSummaryResult:
    title_lower = pr.title.lower()
    body_lower = (pr.body or "").lower()

    # Detect breaking changes
    breaking = []
    if "breaking" in title_lower or "breaking change" in body_lower or "!" in pr.title.split(":")[0]:
        breaking.append("PR metadata or commit prefix indicates a breaking change")

    # Analyze files changed
    files = pr.files
    total_additions = sum(f.additions for f in files)
    total_deletions = sum(f.deletions for f in files)
    file_names = [f.filename for f in files]

    key_changes = []
    config_files = [f for f in file_names if any(c in f for c in ["config", ".env", "settings", "docker", "workflow", ".yml", ".yaml"])]
    test_files = [f for f in file_names if any(t in f.lower() for t in ["test", "spec"])]
    core_files = [f for f in file_names if f not in test_files and f not in config_files]

    if core_files:
        key_changes.append(f"Updated core implementation across {len(core_files)} source files ({', '.join(core_files[:3])}{'...' if len(core_files) > 3 else ''})")
    if test_files:
        key_changes.append(f"Added or modified {len(test_files)} test suite file(s)")
    if config_files:
        key_changes.append(f"Altered infrastructure/configuration files: {', '.join(config_files[:3])}")
    if not key_changes:
        key_changes.append(f"Modified {len(files)} file(s) with +{total_additions}/-{total_deletions} line delta")

    # Risk level determination
    risk_level = "low"
    risk_reasons = []

    if breaking:
        risk_level = "high"
        risk_reasons.append("Contains declared breaking changes")
    if total_additions + total_deletions > 800:
        risk_level = "high" if risk_level != "urgent" else risk_level
        risk_reasons.append(f"Large diff (+{total_additions}/-{total_deletions}) increases chance of regression")
    elif total_additions + total_deletions > 300:
        risk_level = "medium" if risk_level == "low" else risk_level
        risk_reasons.append("Moderate code surface change")

    if any("auth" in f.lower() or "security" in f.lower() or "token" in f.lower() for f in file_names):
        risk_level = "high"
        risk_reasons.append("Touches sensitive authentication or security code")
    if any("migration" in f.lower() or "schema" in f.lower() for f in file_names):
        risk_level = "high"
        risk_reasons.append("Modifies database schema or data migrations")

    if not risk_reasons:
        risk_reasons.append("Isolated changes with manageable blast radius")

    # TLDR
    tldr = f"PR #{pr.number} by @{pr.author} updates {len(files)} files (+{total_additions} / -{total_deletions}): {pr.title}."

    # Architectural impact
    if any("migration" in f.lower() for f in file_names):
        arch_impact = "Database schema altered. Requires migration review and backward compatibility verification."
    elif any("api" in f.lower() or "route" in f.lower() for f in file_names):
        arch_impact = "Public API surface or route handlers updated. Check response schemas and versioning."
    elif config_files:
        arch_impact = "Configuration/CI pipeline modified. Inspect environment variable defaults and deployment scripts."
    else:
        arch_impact = "Low architectural impact. Confined to internal package logic."

    # Review checklist
    review_checklist = [
        "Verify existing test suite passes and edge cases are covered",
        "Inspect git diff for unintentional file changes, formatting, or debug code",
        "Confirm documentation / README updates match the implementation",
    ]
    if breaking:
        review_checklist.append("Verify deprecation notices and migration guide for existing users")
    if config_files:
        review_checklist.append("Test environment variables with missing or default values")

    # Generate markdown format
    md_lines = [
        f"### 🤖 PR #{pr.number} Copilot Summary",
        f"**TL;DR:** {tldr}",
        "",
        "#### Key Changes",
        *[f"- {c}" for c in key_changes],
        "",
        f"**Architectural Impact:** {arch_impact}",
        f"**Risk Level:** `{risk_level.upper()}` ({', '.join(risk_reasons)})",
    ]
    if breaking:
        md_lines.extend(["", "⚠️ **Breaking Changes Detected:**", *[f"- {b}" for b in breaking]])

    return PRSummaryResult(
        number=pr.number,
        title=pr.title,
        tldr=tldr,
        key_changes=key_changes,
        architectural_impact=arch_impact,
        breaking_changes=breaking,
        risk_level=risk_level,
        risk_reasons=risk_reasons,
        review_checklist=review_checklist,
        markdown_summary="\n".join(md_lines),
    )


def summarize_pull_request(pr: PRSummaryRequest) -> PRSummaryResult:
    if not settings.openai_api_key:
        return _heuristic_pr_summary(pr)

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        files_overview = [
            f"{f.filename} (+{f.additions}/-{f.deletions})\nPatch excerpt:\n{f.patch[:400] if f.patch else '(no patch)'}"
            for f in pr.files[:15]
        ]
        context = (
            f"PR #{pr.number}: {pr.title}\n"
            f"Author: @{pr.author}\n"
            f"Description:\n{pr.body or '(No description)'}\n\n"
            f"Files Changed ({len(pr.files)} total):\n" + "\n---\n".join(files_overview)
        )

        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": PR_SUMMARY_PROMPT},
                {"role": "user", "content": context},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        data = json.loads(response.choices[0].message.content or "{}")

        tldr = data.get("tldr", f"PR #{pr.number}: {pr.title}")
        key_changes = data.get("key_changes", [])
        arch = data.get("architectural_impact", "No major architectural impact.")
        breaking = data.get("breaking_changes", [])
        risk_level = data.get("risk_level", "medium").lower()
        risk_reasons = data.get("risk_reasons", [])
        checklist = data.get("review_checklist", [])

        md_lines = [
            f"### 🤖 PR #{pr.number} Copilot Summary",
            f"**TL;DR:** {tldr}",
            "",
            "#### Key Changes",
            *[f"- {c}" for c in key_changes],
            "",
            f"**Architectural Impact:** {arch}",
            f"**Risk Level:** `{risk_level.upper()}`",
        ]
        if breaking:
            md_lines.extend(["", "⚠️ **Breaking Changes Detected:**", *[f"- {b}" for b in breaking]])

        return PRSummaryResult(
            number=pr.number,
            title=pr.title,
            tldr=tldr,
            key_changes=key_changes,
            architectural_impact=arch,
            breaking_changes=breaking,
            risk_level=risk_level,
            risk_reasons=risk_reasons,
            review_checklist=checklist,
            markdown_summary="\n".join(md_lines),
        )
    except Exception:
        return _heuristic_pr_summary(pr)
