from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.config import get_settings

SYSTEM_PROMPT = (
    "Eres un analista legal de contratos empresariales. "
    "Debes responder exclusivamente con JSON válido, sin markdown, "
    "siguiendo exactamente el schema solicitado."
)


def analyze_contract_with_ai(*, contract_text: str, rules_result: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY no está configurado")

    client = OpenAI(api_key=settings.openai_api_key)

    schema_text = {
        "ruleset": "RULES_V1",
        "ai_version": "AI_V1",
        "summary": {
            "executive_summary": "string (8-12 líneas)",
            "overall_risk_level": "LOW|MEDIUM|HIGH",
            "overall_risk_score": "0-100",
        },
        "key_risks": [
            {
                "category": "penalties|payment_terms|renewal|sla|liability|jurisdiction|termination|confidentiality|data|other",
                "severity": "LOW|MEDIUM|HIGH",
                "title": "string",
                "explanation": "string",
                "recommended_action": "string",
                "evidence": ["short quote/snippet <=200 chars"],
            }
        ],
        "negotiation_points": [
            {
                "title": "string",
                "proposed_clause": "string (opcional)",
                "why": "string",
            }
        ],
        "missing_or_ambiguous": [{"item": "string", "why": "string"}],
    }

    user_prompt = (
        "Analiza el contrato usando contract_text + rules_result. "
        "La respuesta DEBE ser JSON válido y nada más.\n\n"
        "Reglas obligatorias:\n"
        "1) Usa ruleset='RULES_V1' y ai_version='AI_V1'.\n"
        "2) executive_summary debe tener 8-12 líneas en texto claro.\n"
        "3) overall_risk_level: LOW|MEDIUM|HIGH y overall_risk_score: entero 0-100.\n"
        "4) key_risks debe incluir evidencia textual real tomada del contrato (snippets <=200 chars).\n"
        "5) Si no hay riesgos, devuelve key_risks, negotiation_points y missing_or_ambiguous como listas vacías y summary coherente.\n"
        "6) No inventes hechos fuera del texto.\n\n"
        f"Schema esperado (guía de tipos):\n{json.dumps(schema_text, ensure_ascii=False, indent=2)}\n\n"
        f"Metadata:\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n\n"
        f"rules_result:\n{json.dumps(rules_result, ensure_ascii=False, indent=2)}\n\n"
        f"contract_text:\n{contract_text}"
    )

    response = client.chat.completions.create(
        model=settings.openai_model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("OpenAI devolvió respuesta vacía")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI no devolvió JSON válido") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("La salida IA no es un objeto JSON")

    parsed.setdefault("ruleset", "RULES_V1")
    parsed.setdefault("ai_version", "AI_V1")

    return parsed
