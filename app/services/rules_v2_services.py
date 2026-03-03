from __future__ import annotations

import re
from typing import Any

_ALLOWED_RULESET = "RULES_V2_SERVICES"
_SCORE_BY_SEVERITY = {"LOW": 5, "MEDIUM": 15, "HIGH": 30}


def _normalize_number(raw: str) -> float:
    s = raw.strip().replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def _extract_percent_values(text: str) -> list[float]:
    values: list[float] = []
    for match in re.finditer(r"(\d{1,3}(?:[.,]\d+)?)\s*%", text, flags=re.IGNORECASE):
        try:
            values.append(_normalize_number(match.group(1)))
        except ValueError:
            continue
    return values


def _extract_amounts_usd(text: str) -> list[float]:
    values: list[float] = []
    amount_pattern = re.compile(
        r"(?:\bUSD\s*\$?|\bUS\$|\$|\bS\/\s*)(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)",
        flags=re.IGNORECASE,
    )
    for match in amount_pattern.finditer(text):
        try:
            values.append(_normalize_number(match.group(1)))
        except ValueError:
            continue
    return values


def _extract_days(text: str) -> list[int]:
    days: list[int] = []
    day_pattern = re.compile(r"(\d{1,4})\s*d[ií]as?(?:\s*calendario)?", flags=re.IGNORECASE)
    month_pattern = re.compile(r"(\d{1,3})\s*mes(?:es)?", flags=re.IGNORECASE)

    for match in day_pattern.finditer(text):
        days.append(int(match.group(1)))

    for match in month_pattern.finditer(text):
        days.append(int(match.group(1)) * 30)

    return days


def _extract_cap(text: str) -> str | None:
    cap_pattern = re.compile(
        r"(?:hasta\s+un\s+m[aá]ximo\s+del?|tope\s+de|cap\s+de)\s*(\d{1,3}(?:[.,]\d+)?)\s*%",
        flags=re.IGNORECASE,
    )
    match = cap_pattern.search(text)
    if not match:
        return None
    return f"{match.group(1)}%"


def _extract_evidence(text: str, pattern: str, max_items: int = 3, radius: int = 100) -> list[str]:
    evidence: list[str] = []
    for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
        start = max(0, match.start() - radius)
        end = min(len(text), match.end() + radius)
        snippet = " ".join(text[start:end].split())
        evidence.append(snippet[:200])
        if len(evidence) >= max_items:
            break
    return evidence


def _finding(category: str, severity: str, title: str, details: str, evidence: list[str], extracted: dict[str, Any]) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "category": category,
        "severity": severity,
        "title": title,
        "details": details,
        "evidence": evidence,
        "extracted": extracted,
    }
    return finding


def analyze_services_rules(text: str) -> dict[str, Any]:
    catalog = [
        ("sla", "HIGH", "SLA detectado", r"\bSLA\b|nivel(?:es)?\s+de\s+servicio|disponibilidad\s*m[ií]nima"),
        ("penalties", "HIGH", "Penalidades o multas", r"penalidad(?:es)?|multa(?:s)?|cl[aá]usula\s+penal"),
        ("payment_terms", "MEDIUM", "Condiciones de pago", r"plazo\s+de\s+pago|facturaci[oó]n|pago\s+(?:se\s+realizar[aá]\s+)?a\s+\d+\s*d[ií]as|contra\s+factura"),
        ("renewal", "MEDIUM", "Renovación automática", r"renovaci[oó]n\s+autom[aá]tica|pr[oó]rroga\s+autom[aá]tica"),
        ("termination", "HIGH", "Terminación o resolución", r"terminaci[oó]n|resoluci[oó]n\s+anticipada|rescisi[oó]n"),
        ("liability", "HIGH", "Responsabilidad y límites", r"responsabilidad|limitaci[oó]n\s+de\s+responsabilidad|tope\s+de\s+responsabilidad"),
        ("warranty_support", "MEDIUM", "Garantía y soporte", r"garant[ií]a|soporte\s+t[eé]cnico|mesa\s+de\s+ayuda"),
        ("scope_change", "MEDIUM", "Cambio de alcance", r"cambio\s+de\s+alcance|control\s+de\s+cambios|adenda"),
        ("confidentiality_data", "HIGH", "Confidencialidad y datos", r"confidencialidad|protecci[oó]n\s+de\s+datos|datos\s+personales"),
        ("dispute_jurisdiction", "MEDIUM", "Disputas y jurisdicción", r"arbitraje|jurisdicci[oó]n|tribunales"),
    ]

    findings: list[dict[str, Any]] = []
    all_percentages = _extract_percent_values(text)
    all_amounts = _extract_amounts_usd(text)
    all_days = _extract_days(text)
    cap = _extract_cap(text)

    for category, severity, title, pattern in catalog:
        evidence = _extract_evidence(text, pattern)
        if not evidence:
            continue

        extracted: dict[str, Any] = {}
        if all_amounts:
            extracted["amounts_usd"] = all_amounts
        if all_percentages:
            extracted["percent_values"] = all_percentages
        if all_days:
            extracted["days"] = all_days
        if cap:
            extracted["cap"] = cap

        findings.append(
            _finding(
                category=category,
                severity=severity,
                title=title,
                details=f"Se detectaron cláusulas relacionadas con {category}.",
                evidence=evidence,
                extracted=extracted,
            )
        )

    risk_score = sum(_SCORE_BY_SEVERITY[f["severity"]] for f in findings)
    if risk_score >= 50:
        risk_level = "HIGH"
    elif risk_score >= 20:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "ruleset": _ALLOWED_RULESET,
        "summary": {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "total_findings": len(findings),
            "critical_flags": sum(1 for f in findings if f["severity"] == "HIGH"),
        },
        "findings": findings,
    }
