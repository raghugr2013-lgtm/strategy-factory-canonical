"""
AI-powered strategy analysis engine.
Generates strengths, weaknesses, risk level, and suggestions.
"""



async def analyze_strategy(strategy_text: str, backtest_results: dict = None) -> dict:
    """Offline analysis (LLM disabled)"""

    return {
        "strengths": [
            "Simple strategy structure",
            "Clear entry/exit logic",
            "Easy to execute"
        ],
        "weaknesses": [
            "No advanced confirmation",
            "May fail in volatile market",
            "Limited risk filtering"
        ],
        "risk_level": "medium",
        "suggestions": [
            "Add confirmation indicators",
            "Improve risk management",
            "Test across multiple market conditions"
        ],
        "raw": "LLM disabled - offline mode"
    }


def _parse_analysis(raw: str) -> dict:
    """Parse the structured AI response into a dict."""
    result = {
        "strengths": [],
        "weaknesses": [],
        "risk_level": "medium",
        "suggestions": [],
        "raw": raw,
    }

    current_section = None
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        upper = line.upper()
        if upper.startswith("STRENGTHS"):
            current_section = "strengths"
            continue
        elif upper.startswith("WEAKNESSES"):
            current_section = "weaknesses"
            continue
        elif upper.startswith("RISK_LEVEL"):
            parts = line.split(":", 1)
            if len(parts) > 1:
                level = parts[1].strip().lower()
                if level in ("low", "medium", "high"):
                    result["risk_level"] = level
                elif "low" in level:
                    result["risk_level"] = "low"
                elif "high" in level:
                    result["risk_level"] = "high"
                else:
                    result["risk_level"] = "medium"
            current_section = None
            continue
        elif upper.startswith("SUGGESTIONS"):
            current_section = "suggestions"
            continue

        if current_section and line.startswith("-"):
            point = line.lstrip("- ").strip()
            if point:
                result[current_section].append(point)

    return result
