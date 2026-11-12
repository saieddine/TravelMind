"""Run a single controlled LLM smoke call or route user intent to offline Destination Agent.

Default is OFFLINE. --live-llm allows one OpenRouter request; Amap is never called.
"""
from __future__ import annotations

import argparse
import json

from llm.openrouter_client import OpenRouterClient, load_local_env
from llm.intent_interpreter import parse_intent, SYSTEM, ClarificationRequired


def run(mode: str, text: str, *, live_llm: bool = False,
        allow_paid_model: bool = False, model: str | None = None,
        client: OpenRouterClient | None = None) -> dict:
    if mode not in {"smoke", "intent", "destination"}:
        raise ValueError("Invalid mode")
    if not isinstance(text, str) or not text.strip() or len(text) > 600:
        raise ValueError("Text must be between 1 and 600 characters")

    usage = {"llm_requests_attempted": 0, "llm_input_tokens": 0,
             "llm_output_tokens": 0, "llm_total_tokens": 0,
             "llm_cost_usd_reported": None, "amap_requests_attempted": 0}
    if not live_llm:
        if mode == "smoke":
            return {"stage": 17, "mode": "offline_smoke", "result": "No LLM call (run with --live-llm)",
                    "usage": usage}
        from agents.destination_agent import understand_locally
        local = understand_locally(text)
        intent = {"city": local["city"], "interests": local["interests"],
                  "category": local["category"], "status": "deterministic_offline_intent",
                  "contains_verified_travel_facts": False}
        trace = [{"step": "local_interpretation", "external_requests": 0}]
    else:
        if client is None:
            load_local_env()
            client = OpenRouterClient(model=model)
        system = "Reply with exactly the word OK." if mode == "smoke" else SYSTEM
        user = "Connection test. Reply OK only." if mode == "smoke" else text
        llm_result = client.complete(system=system, user=user, live=True,
                                     allow_paid_model=allow_paid_model, smoke_test=(mode == "smoke"))
        usage.update(llm_result["usage"])
        trace = llm_result["trace"]
        if mode == "smoke":
            return {"stage": 17, "mode": "live_llm_smoke", "provider": "openrouter",
                    "model": llm_result["model"], "response": llm_result["text"],
                    "usage": usage, "trace": trace}
        intent = parse_intent(llm_result["text"], strict=True)

    if mode == "intent":
        return {"stage": 17, "mode": "live_llm_intent" if live_llm else "offline_intent",
                "intent": intent, "usage": usage, "trace": trace}

    from agents.destination_agent import DestinationAgent
    # In live-LLM mode, pass extracted hints to the existing agent; ai=False prevents
    # a SECOND model call, and live=False prevents an Amap call.
    try:
        destination = DestinationAgent(max_places=4).run_candidates(
            text, city=intent.get("city"), interests=intent.get("interests"),
            category=intent.get("category"), ai=False, live=False,
            interpreted_intent=intent if live_llm else None,
        )
    except ClarificationRequired as exc:
        exc.usage.update(usage)
        exc.trace = trace + exc.trace
        raise

    destination["mode"] = "live_llm_plus_offline_destination" if live_llm else "offline_destination"
    destination["usage"].update(usage)
    destination["trace"] = trace + destination["trace"]
    destination["llm_intent"] = intent
    destination["warnings"].append("LLM selected interests only; attraction data is offline and unverified.")
    destination["stage"] = 17
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="TravelMind Stage 17: capped one-call OpenRouter integration")
    parser.add_argument("--mode", choices=["smoke", "intent", "destination"], default="smoke")
    parser.add_argument("--text", default="I love history and museums in Xi'an")
    parser.add_argument("--live-llm", action="store_true", help="Explicitly authorize exactly one model request")
    parser.add_argument("--allow-paid-model", action="store_true", help="Legacy option; paid models remain blocked")
    parser.add_argument("--model", help="OpenRouter model ID; overrides OPENROUTER_MODEL")
    args = parser.parse_args()
    try:
        result = run(args.mode, args.text, live_llm=args.live_llm,
                     allow_paid_model=args.allow_paid_model, model=args.model)
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, f"Stage 17 failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
