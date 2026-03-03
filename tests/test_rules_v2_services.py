from app.services.rules_v2_services import analyze_services_rules


def test_services_rules_detects_sla_penalties_and_terms() -> None:
    text = (
        "El SLA exige disponibilidad mínima de 99.5% mensual. "
        "Se aplicará penalidad de 0.5% hasta un máximo del 5% del valor del contrato. "
        "El pago se realizará a 60 días calendario contra factura por USD $4,500,000.00."
    )

    result = analyze_services_rules(text)

    assert result["ruleset"] == "RULES_V2_SERVICES"
    assert result["summary"]["total_findings"] >= 3
    assert result["summary"]["risk_score"] >= 60

    categories = {f["category"] for f in result["findings"]}
    assert "sla" in categories
    assert "penalties" in categories
    assert "payment_terms" in categories
