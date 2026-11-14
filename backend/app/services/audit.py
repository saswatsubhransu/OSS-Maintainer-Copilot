import json
import re
from typing import List, Dict, Tuple
from openai import OpenAI

from app.config import settings
from app.schemas import PRAuditRequest, PRAuditResult, PRFileItem


AUDIT_PROMPT = """You are an open-source code quality auditor.
Analyze the following Pull Request diff and files to check for:
1. Missing unit or integration tests for new/modified logic.
2. Missing documentation (README, docstrings, API specs, user guide).

Respond ONLY with a JSON object:
{
  "readiness": "Ready for Review" | "Needs Tests" | "Needs Docs" | "Needs Tests & Docs",
  "test_status": "ok" | "warning" | "missing",
  "docs_status": "ok" | "warning" | "missing",
  "test_findings": ["Specific observation about missing test coverage 1", "observation 2"],
  "docs_findings": ["Specific observation about missing documentation 1", "observation 2"],
  "suggested_test_scaffold": "// Code snippet of recommended test file/cases",
  "suggested_doc_snippet": "### Documentation snippet for README or docstrings",
  "recommended_action": "Clear recommendation message for the PR author"
}
"""


def _detect_languages_and_patterns(files: List[PRFileItem]) -> Tuple[str, List[str], List[str], List[str]]:
    source_files = []
    test_files = []
    doc_files = []
    lang = "python"

    for f in files:
        name = f.filename.lower()
        if any(name.endswith(ext) for ext in [".md", ".rst", ".txt", ".adoc", "doc/", "docs/"]):
            doc_files.append(f.filename)
        elif any(pattern in name for pattern in ["test_", "_test.", ".test.", ".spec.", "tests/", "spec/", "__tests__/"]):
            test_files.append(f.filename)
        elif any(name.endswith(ext) for ext in [".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cpp", ".c"]):
            source_files.append(f.filename)
            if name.endswith((".ts", ".tsx")):
                lang = "typescript"
            elif name.endswith((".js", ".jsx")):
                lang = "javascript"
            elif name.endswith(".go"):
                lang = "go"
            elif name.endswith(".rs"):
                lang = "rust"
            elif name.endswith(".py"):
                lang = "python"

    return lang, source_files, test_files, doc_files


def _heuristic_audit(pr: PRAuditRequest) -> PRAuditResult:
    lang, source_files, test_files, doc_files = _detect_languages_and_patterns(pr.files)

    test_findings = []
    docs_findings = []

    # Check tests
    if source_files and not test_files:
        test_status = "missing"
        test_findings.append(f"PR modifies {len(source_files)} core source file(s) ({', '.join(source_files[:3])}) but contains no test files.")
        test_findings.append("No automated test suite coverage added for new or altered logic.")
    elif source_files and test_files:
        test_status = "ok"
        test_findings.append(f"Test files detected ({', '.join(test_files[:3])}). Ensure boundary cases are covered.")
    else:
        test_status = "ok"
        test_findings.append("No core source code logic changes requiring tests.")

    # Check documentation
    touches_config_or_api = any(
        any(k in f.filename.lower() for k in ["config", "api", "route", "cli", "env", "settings", "schema"])
        for f in pr.files
    )

    if touches_config_or_api and not doc_files:
        docs_status = "warning"
        docs_findings.append("PR touches public API or configuration interfaces, but does not update README, docs, or user guide.")
    elif doc_files:
        docs_status = "ok"
        docs_findings.append(f"Documentation files updated: {', '.join(doc_files[:2])}.")
    else:
        docs_status = "ok"
        docs_findings.append("Internal change; external documentation update not strictly required.")

    # Overall readiness
    if test_status == "missing" and docs_status == "warning":
        readiness = "Needs Tests & Docs"
    elif test_status == "missing":
        readiness = "Needs Tests"
    elif docs_status == "warning":
        readiness = "Needs Docs"
    else:
        readiness = "Ready for Review"

    # Generate scaffold code
    scaffold = ""
    target_name = source_files[0] if source_files else "feature_module"
    base_name = target_name.split("/")[-1].split(".")[0]

    if lang == "python":
        scaffold = f"""import pytest
from app.{base_name} import *

def test_{base_name}_happy_path():
    # TODO: Verify expected output with standard valid input
    result = execute_action()
    assert result is not None

def test_{base_name}_invalid_input_raises_error():
    # TODO: Verify graceful failure on invalid/empty parameter
    with pytest.raises(ValueError):
        execute_action(invalid_parameter=True)

def test_{base_name}_boundary_conditions():
    # TODO: Verify edge case behavior (e.g. empty list, None, unicode)
    assert True
"""
    elif lang in ["typescript", "javascript"]:
        scaffold = f"""import {{ describe, it, expect }} from 'vitest'; // or jest
import {{ {base_name} }} from '../{target_name}';

describe('{base_name}', () => {{
  it('handles standard input successfully', () => {{
    const res = {base_name}();
    expect(res).toBeDefined();
  }});

  it('rejects invalid inputs gracefully', () => {{
    expect(() => {base_name}(null as any)).toThrow();
  }});

  it('supports boundary conditions', () => {{
    // Verify edge cases and empty payloads
  }});
}});
"""
    else:
        scaffold = f"""// Unit test scaffold for {target_name}
// Test cases needed:
// 1. Happy path execution with standard arguments
// 2. Error handling when required fields are missing
// 3. Boundary values / empty state handling
"""

    # Generate doc snippet
    doc_snippet = f"""## Updates in PR #{pr.number}

### Usage & Configuration
If this change introduces new options or parameters, document them below:

```markdown
### Configuration Options
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `ENABLE_{base_name.upper()}` | boolean | `false` | Enables {pr.title} |
```

### Example
Describe how users or developers should use the new capability.
"""

    recommended_action = (
        f"Request the contributor to add unit tests covering `{target_name}` before merging."
        if test_status == "missing"
        else "PR passes automated tests and docs audit. Proceed to human peer review."
    )

    return PRAuditResult(
        number=pr.number,
        readiness=readiness,
        test_status=test_status,
        docs_status=docs_status,
        test_findings=test_findings,
        docs_findings=docs_findings,
        suggested_test_scaffold=scaffold,
        suggested_doc_snippet=doc_snippet,
        recommended_action=recommended_action,
    )


def audit_pull_request(pr: PRAuditRequest) -> PRAuditResult:
    if not settings.openai_api_key:
        return _heuristic_audit(pr)

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        files_summary = "\n".join(
            f"- {f.filename} ({f.status}, +{f.additions}/-{f.deletions})"
            for f in pr.files[:20]
        )
        context = (
            f"PR #{pr.number}: {pr.title}\n"
            f"Body:\n{pr.body or '(None)'}\n\n"
            f"Changed Files:\n{files_summary}"
        )

        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": AUDIT_PROMPT},
                {"role": "user", "content": context},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        data = json.loads(response.choices[0].message.content or "{}")
        return PRAuditResult(
            number=pr.number,
            readiness=data.get("readiness", "Ready for Review"),
            test_status=data.get("test_status", "ok"),
            docs_status=data.get("docs_status", "ok"),
            test_findings=data.get("test_findings", []),
            docs_findings=data.get("docs_findings", []),
            suggested_test_scaffold=data.get("suggested_test_scaffold", ""),
            suggested_doc_snippet=data.get("suggested_doc_snippet", ""),
            recommended_action=data.get("recommended_action", "Review PR changes"),
        )
    except Exception:
        return _heuristic_audit(pr)
