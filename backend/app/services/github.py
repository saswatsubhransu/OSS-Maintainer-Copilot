import hmac
import hashlib
from typing import List, Dict, Any, Optional
import httpx
from fastapi import HTTPException

from app.config import settings


def get_github_headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "OSS-Maintainer-Copilot",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


async def list_issues(owner: str, repo: str, state: str = "open", per_page: int = 30) -> List[Dict[str, Any]]:
    if state not in {"open", "closed", "all"}:
        raise HTTPException(status_code=400, detail="state must be open, closed, or all")
    if not (1 <= per_page <= 100):
        raise HTTPException(status_code=400, detail="per_page must be between 1 and 100")

    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    headers = get_github_headers()

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(
            url, headers=headers, params={"state": state, "per_page": per_page, "sort": "created", "direction": "desc"}
        )

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Repository not found or not accessible")
    if response.status_code == 403:
        raise HTTPException(status_code=403, detail="GitHub rate limit exceeded or access restricted. Set GITHUB_TOKEN in backend/.env for 5,000 req/hr.")
    if response.is_error:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {response.text[:200]}")

    results = []
    for item in response.json():
        # Exclude pull requests from regular issues list
        is_pr = "pull_request" in item
        results.append({
            "number": item["number"],
            "title": item["title"],
            "body": item.get("body") or "",
            "html_url": item["html_url"],
            "state": item["state"],
            "author": item.get("user", {}).get("login", "unknown"),
            "labels": [label["name"] for label in item.get("labels", [])],
            "is_pull_request": is_pr,
            "created_at": item.get("created_at"),
            "comments_count": item.get("comments", 0),
        })
    return results


async def list_pull_requests(owner: str, repo: str, state: str = "open", per_page: int = 30) -> List[Dict[str, Any]]:
    if state not in {"open", "closed", "all"}:
        raise HTTPException(status_code=400, detail="state must be open, closed, or all")

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = get_github_headers()

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(
            url, headers=headers, params={"state": state, "per_page": per_page, "sort": "created", "direction": "desc"}
        )

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Repository not found or not accessible")
    if response.status_code == 403:
        raise HTTPException(status_code=403, detail="GitHub rate limit exceeded. Provide GITHUB_TOKEN in backend/.env.")
    if response.is_error:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {response.text[:200]}")

    results = []
    for item in response.json():
        results.append({
            "number": item["number"],
            "title": item["title"],
            "body": item.get("body") or "",
            "html_url": item["html_url"],
            "state": item["state"],
            "author": item.get("user", {}).get("login", "unknown"),
            "labels": [label["name"] for label in item.get("labels", [])],
            "draft": item.get("draft", False),
            "merged_at": item.get("merged_at"),
            "created_at": item.get("created_at"),
            "head_ref": item.get("head", {}).get("ref", ""),
            "base_ref": item.get("base", {}).get("ref", ""),
        })
    return results


async def get_pull_request_files(owner: str, repo: str, pull_number: int) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}/files"
    headers = get_github_headers()

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(url, headers=headers, params={"per_page": 50})

    if response.is_error:
        return []

    files = []
    for f in response.json():
        files.append({
            "filename": f.get("filename", ""),
            "status": f.get("status", "modified"),
            "additions": f.get("additions", 0),
            "deletions": f.get("deletions", 0),
            "changes": f.get("changes", 0),
            "patch": (f.get("patch") or "")[:2500],  # Keep reasonable patch chunk
        })
    return files


async def list_merged_pull_requests(owner: str, repo: str, per_page: int = 40) -> List[Dict[str, Any]]:
    # Closed PRs can be merged or unmerged; filter for merged
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = get_github_headers()

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(
            url, headers=headers, params={"state": "closed", "per_page": per_page, "sort": "updated", "direction": "desc"}
        )

    if response.is_error:
        return []

    merged_prs = []
    for item in response.json():
        if item.get("merged_at"):
            merged_prs.append({
                "number": item["number"],
                "title": item["title"],
                "body": item.get("body") or "",
                "author": item.get("user", {}).get("login", "unknown"),
                "labels": [label["name"] for label in item.get("labels", [])],
                "merged_at": item.get("merged_at"),
            })
    return merged_prs


def verify_webhook_signature(payload_bytes: bytes, signature_header: Optional[str], secret: str) -> bool:
    if not secret:
        # If no secret configured in backend, allow in dev mode
        return True
    if not signature_header:
        return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False

    given_signature = signature_header[len(prefix):]
    expected_signature = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(given_signature, expected_signature)
