"""Bounded excerpts with original job/line references; redaction is best effort."""
import re

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
TIME_PREFIX = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z\s*")
ERROR = re.compile(r"(?i)(traceback|\bexception\b|\berror\b|##\[error\]|\bfailed\b|failure|"
                   r"ModuleNotFoundError|ImportError|AssertionError|SyntaxError|KeyError|"
                   r"not found|permission denied|timed out|exit code [1-9])")


def redact(text: str, secrets: list[str]) -> str:
    for secret in sorted(secrets, key=len, reverse=True):
        if len(secret) >= 8:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----", "[REDACTED PRIVATE KEY]", text)
    text = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIza[A-Za-z0-9_-]{30,}|AKIA[A-Z0-9]{16})\b", "[REDACTED TOKEN]", text)
    text = re.sub(r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)\S+", r"\1[REDACTED]", text)
    text = re.sub(r"(?im)((?:api[_-]?key|access[_-]?token|secret|password|passwd|client_secret|aws_secret_access_key)\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", text)
    text = re.sub(r"(https?://)[^\s/@:]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b", "[REDACTED JWT]", text)
    return ANSI.sub("", text)


def excerpt_for_job(text: str, job: dict, budget: int) -> list[dict]:
    lines = text.splitlines()
    # Keep line numbers tied to the original downloaded job log.
    cleaned = [TIME_PREFIX.sub("", line).replace("\x00", "")[:1500] for line in lines]
    hits = [i for i, line in enumerate(cleaned) if ERROR.search(line)]
    selected: set[int] = set()
    candidates: list[int] = []
    # Prefer late error groups; CI often prints many irrelevant earlier warnings.
    for hit in reversed(hits[-35:]):
        candidates.extend(range(max(0, hit - 4), min(len(lines), hit + 6)))
    candidates.extend(range(max(0, len(lines) - 35), len(lines)))
    used = 0
    for index in candidates:
        if index in selected or not cleaned[index].strip():
            continue
        cost = len(cleaned[index]) + 80
        if used + cost > budget:
            continue
        selected.add(index)
        used += cost
    return [{"id": f"job{int(job['id'])}:L{i+1}", "job_id": int(job["id"]),
             "job_name": str(job.get("name", "Job"))[:200], "line": i + 1, "text": cleaned[i]}
            for i in sorted(selected)]


def validate_evidence(analysis: dict, excerpt: list[dict]) -> tuple[dict, str]:
    lookup = {line["id"]: line for line in excerpt}
    requested = analysis["evidence_ids"]
    valid = [lookup[key] for key in dict.fromkeys(requested) if key in lookup]
    invalid = any(key not in lookup for key in requested)
    inconclusive = analysis["insufficient_evidence"] or invalid or not valid
    result = dict(analysis)
    result["evidence"] = valid
    result["evidence_check"] = "References exist in the excerpt; this does not prove the diagnosis."
    if inconclusive:
        result.update(category="Unknown", insufficient_evidence=True, uncertainty="high",
                      root_cause="The available excerpt did not support a reliable explanation.",
                      suggested_fix="Review the failed job on GitHub. More log context may be needed.")
        if invalid:
            result["evidence_check"] = "Gemini cited a line outside the supplied excerpt; the explanation was withheld."
    return result, "inconclusive" if inconclusive else "completed"
