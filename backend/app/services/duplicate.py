import json
import re
import math
from typing import List, Dict, Set, Tuple
from collections import Counter
from openai import OpenAI

from app.config import settings
from app.schemas import (
    DuplicateDetectRequest,
    DuplicateDetectResult,
    DuplicateMatch,
    IssueItem,
)


STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "should", "shouldn't", "so", "some", "such", "than", "that", "the", "their",
    "theirs", "them", "themselves", "then", "there", "these", "they", "this",
    "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "wasn't", "we", "were", "weren't", "what", "when", "where", "which", "while",
    "who", "whom", "why", "with", "won't", "would", "wouldn't", "you", "your",
    "yours", "yourself", "yourselves", "issue", "bug", "error", "problem"
}


def tokenize(text: str) -> List[str]:
    # Extract alphanumeric words and common programming identifiers (e.g. foo_bar, baz.qux)
    words = re.findall(r"[a-zA-Z0-9_\-\.]+", text.lower())
    return [w for w in words if len(w) > 2 and w not in STOPWORDS]


def extract_technical_terms(text: str) -> Set[str]:
    # Find error types, code mentions, camelCase, snake_case
    terms = set()
    for m in re.finditer(r"([A-Z][a-zA-Z]+Error|[A-Z][a-zA-Z]+Exception)", text):
        terms.add(m.group(1).lower())
    for m in re.finditer(r"`([^`]+)`", text):
        code_token = m.group(1).strip().lower()
        if 2 < len(code_token) < 50:
            terms.add(code_token)
    return terms


def compute_similarity(target: IssueItem, candidate: IssueItem) -> Tuple[float, List[str], List[str]]:
    target_text = f"{target.title} {target.body or ''}"
    candidate_text = f"{candidate.title} {candidate.body or ''}"

    target_tokens = tokenize(target_text)
    candidate_tokens = tokenize(candidate_text)

    if not target_tokens or not candidate_tokens:
        return 0.0, [], []

    # Title similarity (heavily weighted)
    target_title_tokens = set(tokenize(target.title))
    candidate_title_tokens = set(tokenize(candidate.title))
    title_jaccard = (
        len(target_title_tokens & candidate_title_tokens)
        / len(target_title_tokens | candidate_title_tokens)
        if (target_title_tokens | candidate_title_tokens)
        else 0.0
    )

    # Body cosine similarity on term frequencies
    vec1 = Counter(target_tokens)
    vec2 = Counter(candidate_tokens)
    intersection = set(vec1.keys()) & set(vec2.keys())
    numerator = sum(vec1[x] * vec2[x] for x in intersection)
    sum1 = sum(vec1[x] ** 2 for x in vec1.keys())
    sum2 = sum(vec2[x] ** 2 for x in vec2.keys())
    denominator = math.sqrt(sum1) * math.sqrt(sum2)
    body_cosine = numerator / denominator if denominator else 0.0

    # Technical term / error overlap
    target_terms = extract_technical_terms(target_text)
    candidate_terms = extract_technical_terms(candidate_text)
    shared_terms = target_terms & candidate_terms

    # Label overlap
    target_labels = set(target.labels)
    candidate_labels = set(candidate.labels)
    shared_labels = target_labels & candidate_labels

    # Composite score calculation
    score = (0.45 * title_jaccard) + (0.35 * body_cosine)
    if shared_terms:
        score += min(0.25, len(shared_terms) * 0.08)
    if shared_labels:
        score += min(0.1, len(shared_labels) * 0.03)

    score = min(1.0, round(score, 3))

    signals = []
    if title_jaccard > 0.3:
        signals.append(f"High title vocabulary overlap ({int(title_jaccard * 100)}%)")
    if shared_terms:
        signals.append(f"Shared code/error signatures: {', '.join(list(shared_terms)[:3])}")
    if shared_labels:
        signals.append(f"Matching labels: {', '.join(shared_labels)}")
    if body_cosine > 0.4:
        signals.append(f"Strong description similarity ({int(body_cosine * 100)}% lexical match)")

    distinctions = []
    if target.state != candidate.state:
        distinctions.append(f"Issue #{candidate.number} is already {candidate.state}")
    diff_labels = candidate_labels - target_labels
    if diff_labels:
        distinctions.append(f"Candidate has labels not present in target: {', '.join(list(diff_labels)[:2])}")

    return score, signals, distinctions


def detect_duplicates(req: DuplicateDetectRequest) -> DuplicateDetectResult:
    target = req.target_issue
    candidates = [c for c in req.candidate_issues if c.number != target.number]

    scored_matches: List[Tuple[float, IssueItem, List[str], List[str]]] = []
    for cand in candidates:
        score, signals, distinctions = compute_similarity(target, cand)
        if score >= req.threshold:
            scored_matches.append((score, cand, signals, distinctions))

    # Sort descending by score
    scored_matches.sort(key=lambda x: x[0], reverse=True)
    top_candidates = scored_matches[:5]

    matches: List[DuplicateMatch] = []
    for score, cand, signals, distinctions in top_candidates:
        confidence = "low"
        if score >= 0.70:
            confidence = "high"
        elif score >= 0.45:
            confidence = "medium"

        if score >= 0.75:
            rec = f"Probable duplicate. Consider commenting: 'Duplicate of #{cand.number}' and closing."
        elif score >= 0.50:
            rec = f"Related issue or shared root cause. Cross-link to #{cand.number} for discussion."
        else:
            rec = f"Slight thematic similarity to #{cand.number}. Keep both open unless investigation proves shared bug."

        matches.append(
            DuplicateMatch(
                issue_number=cand.number,
                title=cand.title,
                html_url=cand.html_url or f"https://github.com/issues/{cand.number}",
                state=cand.state or "open",
                similarity_score=score,
                confidence=confidence,
                matching_signals=signals or ["Thematic keyword overlap"],
                distinctions=distinctions,
                recommendation=rec,
            )
        )

    has_duplicates = len(matches) > 0 and matches[0].similarity_score >= max(req.threshold, 0.35)

    if not matches:
        summary = f"No likely duplicate issues detected among the {len(candidates)} candidate issues analyzed."
    else:
        top = matches[0]
        summary = (
            f"Found {len(matches)} potential duplicate(s). Top match is #{top.issue_number} "
            f"('{top.title[:50]}...') with {int(top.similarity_score * 100)}% similarity ({top.confidence} confidence)."
        )

    # Optional LLM refinement if OpenAI API key exists and top matches exist
    if settings.openai_api_key and top_candidates:
        try:
            client = OpenAI(api_key=settings.openai_api_key)
            prompt = (
                f"Target Issue #{target.number}: {target.title}\n{target.body[:500]}\n\n"
                f"Candidate Duplicate #{top_candidates[0][1].number}: {top_candidates[0][1].title}\n{top_candidates[0][1].body[:500]}\n\n"
                "Are these two issues talking about the same underlying problem or feature request? "
                "Respond with JSON: {\"is_duplicate\": bool, \"explanation\": str, \"confidence\": \"high\"|\"medium\"|\"low\"}"
            )
            llm_res = client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            parsed = json.loads(llm_res.choices[0].message.content or "{}")
            if parsed.get("explanation"):
                matches[0].recommendation += f" [AI verification: {parsed['explanation']}]"
                if parsed.get("confidence"):
                    matches[0].confidence = parsed["confidence"]
        except Exception:
            pass  # Keep algorithmic assessment

    return DuplicateDetectResult(
        has_duplicates=has_duplicates,
        top_matches=matches,
        analysis_summary=summary,
    )
