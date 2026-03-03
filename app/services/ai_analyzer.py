from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.config import get_settings


SYSTEM_PROMPT = (
    "Eres un analista legal de contratos empresariales. "
    "Devuelve exclusivamente JSON válido (sin markdown, sin texto extra). "
    "No inventes hechos: todo debe estar sustentado en contract_text."
)


def analyze_contract_with_ai(
    *,
    contract_text: str,
    rules_result: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()

    # Mensaje ASCII (evita problemas de encoding tipo 'estÃ¡')
    if not (settings.openai_api_key or "").strip():
        raise RuntimeError("OPENAI_API_KEY no esta configurado")

    client = OpenAI(api_key=settings.openai_api_key)

    schema_guide = {
        "ruleset": "RULES_V1",
        "ai_version": "AI_V1",
        "summary": {
            "executive_summary": "string (8-12 lineas, claro y ejecutivo)",
            "overall_risk_level": "LOW|MEDIUM|HIGH",
            "overall_risk_score": "0-100 (entero)",
        },
        "key_risks": [
            {
                "category": "penalties|payment_terms|renewal|sla|liability|jurisdiction|termination|confidentiality|data|other",
                "severity": "LOW|MEDIUM|HIGH",
                "title": "string",
                "explanation": "string",
                "recommended_action": "string",
                "evidence": ["snippet <=200 chars (texto literal del contrato)"],
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
        "Analiza el contrato usando contract_text + rules_result.\n"
        "Reglas obligatorias:\n"
        "1) Responde SOLO JSON valido.\n"
        "2) Usa ruleset='RULES_V1' y ai_version='AI_V1'.\n"
        "3) executive_summary: 8-12 lineas.\n"
        "4) overall_risk_level: LOW|MEDIUM|HIGH y overall_risk_score: entero 0-100.\n"
        "5) key_risks: evidencia real del contrato (snippets <=200 chars).\n"
        "6) Si no hay riesgos, listas vacias y summary coherente.\n"
        "7) No inventes nada fuera del texto.\n\n"
        f"Schema guia:\n{json.dumps(schema_guide, ensure_ascii=False, indent=2)}\n\n"
        f"Metadata:\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n\n"
        f"rules_result:\n{json.dumps(rules_result, ensure_ascii=False, indent=2)}\n\n"
        f"contract_text:\n{contract_text}"
    )

    resp = client.chat.completions.create(
        model=settings.openai_model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = (resp.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("OpenAI devolvio respuesta vacia")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI no devolvio JSON valido") from exc

    if not isinstance(data, dict):
        raise RuntimeError("La salida IA no es un objeto JSON")

    data.setdefault("ruleset", "RULES_V1")
    data.setdefault("ai_version", "AI_V1")
    return data
