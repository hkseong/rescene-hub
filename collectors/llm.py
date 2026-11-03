"""Claude API wrapper: JSON-schema output, web search, monthly cost ledger."""
from __future__ import annotations

import json

import anthropic

from . import config
from .common import iso, load, now, save

_client = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=3)
    return _client


def month_key() -> str:
    return now().strftime("%Y-%m")


def month_cost() -> float:
    return load("usage.json", {}).get(month_key(), {}).get("usd", 0.0)


def over_budget() -> bool:
    return month_cost() >= config.MONTHLY_BUDGET_SOFT


def _record(model: str, usage, purpose: str) -> float:
    pin, pout = config.PRICES[model]
    tokens_in = (usage.input_tokens or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cached = getattr(usage, "cache_read_input_tokens", 0) or 0
    searches = 0
    stu = getattr(usage, "server_tool_use", None)
    if stu is not None:
        searches = getattr(stu, "web_search_requests", 0) or 0
    usd = (tokens_in * pin + cached * pin * 0.1 + (usage.output_tokens or 0) * pout) / 1e6
    usd += searches * config.WEB_SEARCH_PRICE
    print(f"  [llm] {purpose} {model} in={tokens_in} cached={cached} out={usage.output_tokens} "
          f"search={searches} ${usd:.4f}")
    ledger = load("usage.json", {})
    m = ledger.setdefault(month_key(), {"usd": 0.0, "calls": 0, "searches": 0, "by_purpose": {}})
    m["usd"] = round(m["usd"] + usd, 4)
    m["calls"] += 1
    m["searches"] += searches
    m["by_purpose"][purpose] = round(m["by_purpose"].get(purpose, 0) + usd, 4)
    m["updated"] = iso()
    save("usage.json", ledger)
    return usd


def ask_json(*, model: str, system: str, content, schema: dict, purpose: str,
             web_search: int = 0, effort: str = "medium", max_tokens: int = 16000) -> tuple[dict, list[str]]:
    """Run one request whose final answer must match `schema`.

    Returns (parsed_json, urls_seen_in_web_search_results).
    """
    tools = []
    if web_search:
        tools.append({"type": "web_search_20260209", "name": "web_search", "max_uses": web_search,
                      "user_location": {"type": "approximate", "country": "KR", "timezone": "Asia/Seoul"}})
    messages = [{"role": "user", "content": content}]
    seen_urls: list[str] = []
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    if tools:
        kwargs["tools"] = tools
    for _ in range(4):  # pause_turn 재개 최대 3회
        resp = client().messages.create(messages=messages, **kwargs)
        _record(model, resp.usage, purpose)
        for block in resp.content:
            if block.type == "web_search_tool_result" and isinstance(block.content, list):
                seen_urls.extend(r.url for r in block.content if getattr(r, "url", None))
        if resp.stop_reason == "pause_turn":
            messages = [messages[0], {"role": "assistant", "content": resp.content}]
            continue
        break
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"LLM refusal ({purpose})")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError(f"LLM output truncated ({purpose})")
    texts = [b.text for b in resp.content if b.type == "text"]
    if not texts:
        raise RuntimeError(f"LLM returned no text ({purpose})")
    return json.loads(texts[-1]), seen_urls
