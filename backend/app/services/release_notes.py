import re
from typing import List, Dict, Set
from openai import OpenAI

from app.config import settings
from app.schemas import (
    ReleaseNotesRequest,
    ReleaseNotesResult,
    ReleaseNoteEntry,
    ClosedPRItem,
)


def _calculate_semver_bump(current_version: str, has_breaking: bool, has_feature: bool) -> tuple[str, str, str]:
    # Extract version numbers e.g. v1.2.3 -> [1, 2, 3]
    prefix = "v" if current_version.startswith("v") else ""
    nums = re.findall(r"\d+", current_version)
    if len(nums) < 3:
        major, minor, patch = 0, 1, 0
    else:
        major, minor, patch = int(nums[0]), int(nums[1]), int(nums[2])

    if has_breaking:
        bump_type = "major"
        bump_reason = "Contains breaking changes requiring a major version bump."
        new_version = f"{prefix}{major + 1}.0.0"
    elif has_feature:
        bump_type = "minor"
        bump_reason = "Introduces new features or enhancements without breaking changes."
        new_version = f"{prefix}{major}.{minor + 1}.0"
    else:
        bump_type = "patch"
        bump_reason = "Contains only bug fixes, documentation, or internal maintenance."
        new_version = f"{prefix}{major}.{minor}.{patch + 1}"

    return new_version, bump_type, bump_reason


def generate_release_notes(req: ReleaseNotesRequest) -> ReleaseNotesResult:
    features: List[ReleaseNoteEntry] = []
    bug_fixes: List[ReleaseNoteEntry] = []
    breaking_changes: List[ReleaseNoteEntry] = []
    documentation: List[ReleaseNoteEntry] = []
    maintenance: List[ReleaseNoteEntry] = []
    contributors: Set[str] = set()

    for pr in req.pull_requests:
        author = pr.author or "contributor"
        if author.lower() not in ["dependabot[bot]", "github-actions[bot]", "bot"]:
            contributors.add(author)

        title_lower = pr.title.lower()
        labels_lower = [l.lower() for l in pr.labels]
        body_lower = (pr.body or "").lower()

        # Categorize PR
        if (
            "breaking" in title_lower
            or "breaking change" in body_lower
            or any("breaking" in l for l in labels_lower)
            or "!:" in pr.title
        ):
            breaking_changes.append(ReleaseNoteEntry(title=pr.title, number=pr.number, author=author, category="breaking"))
        elif (
            any(k in title_lower for k in ["feat", "add", "support", "new", "allow", "introduce"])
            or any("enhancement" in l or "feature" in l for l in labels_lower)
        ):
            features.append(ReleaseNoteEntry(title=pr.title, number=pr.number, author=author, category="feature"))
        elif (
            any(k in title_lower for k in ["fix", "bug", "resolve", "patch", "repair", "handle"])
            or any("bug" in l for l in labels_lower)
        ):
            bug_fixes.append(ReleaseNoteEntry(title=pr.title, number=pr.number, author=author, category="fix"))
        elif (
            any(k in title_lower for k in ["doc", "readme", "guide", "tutorial", "typo"])
            or any("documentation" in l for l in labels_lower)
        ):
            documentation.append(ReleaseNoteEntry(title=pr.title, number=pr.number, author=author, category="docs"))
        else:
            maintenance.append(ReleaseNoteEntry(title=pr.title, number=pr.number, author=author, category="chore"))

    has_breaking = len(breaking_changes) > 0
    has_features = len(features) > 0
    recommended_version, bump_type, bump_reason = _calculate_semver_bump(
        req.current_version or "v0.1.0", has_breaking, has_features
    )

    if req.target_version:
        recommended_version = req.target_version

    # Build Markdown
    lines = [
        f"# Release {recommended_version}",
        "",
        f"**Repository:** `{req.owner}/{req.repo}`  ",
        f"**Semantic Bump:** `{bump_type.upper()}` ({bump_reason})",
        "",
    ]

    if breaking_changes:
        lines.append("## ⚠️ Breaking Changes")
        for e in breaking_changes:
            lines.append(f"- {e.title} (#{e.number}) by @{e.author}")
        lines.append("")

    if features:
        lines.append("## 🚀 Features & Enhancements")
        for e in features:
            lines.append(f"- {e.title} (#{e.number}) by @{e.author}")
        lines.append("")

    if bug_fixes:
        lines.append("## 🐛 Bug Fixes")
        for e in bug_fixes:
            lines.append(f"- {e.title} (#{e.number}) by @{e.author}")
        lines.append("")

    if documentation:
        lines.append("## 📚 Documentation")
        for e in documentation:
            lines.append(f"- {e.title} (#{e.number}) by @{e.author}")
        lines.append("")

    if maintenance:
        lines.append("## 🛠️ Maintenance & Chores")
        for e in maintenance:
            lines.append(f"- {e.title} (#{e.number}) by @{e.author}")
        lines.append("")

    sorted_contributors = sorted(list(contributors))
    if sorted_contributors:
        lines.append("## ❤️ New Contributors & Community")
        lines.append(
            "Special thanks to everyone who contributed to this release: "
            + ", ".join(f"@{c}" for c in sorted_contributors)
        )
        lines.append("")

    lines.append(f"**Full Changelog**: https://github.com/{req.owner}/{req.repo}/commits/{recommended_version}")

    return ReleaseNotesResult(
        recommended_version=recommended_version,
        bump_type=bump_type,
        bump_reason=bump_reason,
        features=features,
        bug_fixes=bug_fixes,
        breaking_changes=breaking_changes,
        documentation=documentation,
        maintenance=maintenance,
        contributors=sorted_contributors,
        markdown="\n".join(lines),
    )
