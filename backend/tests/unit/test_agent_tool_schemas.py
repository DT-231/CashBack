"""Schema tool cho Muse AI (OpenAI/Gemini) phải khớp API thật."""
import json
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def load():
    openai = {t["function"]["name"]: t["function"] for t in json.loads((TOOLS / "openai_tools.json").read_text())["tools"]}
    gemini = {t["name"]: t for t in json.loads((TOOLS / "gemini_tools.json").read_text())}
    return openai, gemini


def test_both_providers_define_the_same_tools():
    openai, gemini = load()
    assert set(openai) == set(gemini) and "shopee_insights" in openai


def test_insights_tool_matches_the_endpoint_contract():
    openai, gemini = load()
    for tool in (openai["shopee_insights"], gemini["shopee_insights"]):
        props = tool["parameters"]["properties"]
        assert tool["parameters"]["required"] == ["group"]
        assert props["group"]["enum"] == ["post", "category", "page", "hour"]          # đúng tập giá trị API chấp nhận
        assert (props["days"]["minimum"], props["days"]["maximum"]) == (1, 365)
        assert "người dùng" in tool["description"].lower() or "nguoi dung" in tool["description"].lower()


def test_tool_names_are_valid_function_names():
    import re
    openai, _ = load()
    assert all(re.fullmatch(r"[a-z][a-z0-9_]{2,63}", n) for n in openai)
