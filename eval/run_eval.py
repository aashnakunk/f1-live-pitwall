"""
F1 AI Chat — Eval Harness

Runs a suite of test questions against the chat endpoint and records:
- Response text
- Tools called (name + input)
- Expected vs actual tools (accuracy scoring)
- Token usage (input/output)
- Latency per question
- Keyword presence in response (content relevance)
- Multi-turn conversation support

Results saved to eval/results/<timestamp>.json

Usage:
    # Set your API key
    export ANTHROPIC_API_KEY=sk-ant-...

    # Make sure backend is running on :8000 with a session loaded
    python eval/run_eval.py

    # Or specify a different backend URL
    python eval/run_eval.py --url http://localhost:8000
"""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

import httpx

# ── Test Cases ───────────────────────────────────────────────────────────────
# Each case has:
#   question: what to ask
#   expected_tools: list of tool names that SHOULD be called
#   keywords: words that SHOULD appear in the response (case-insensitive)
#   page: which page context to simulate
#   follow_up: optional follow-up question (tests conversation memory)

TEST_CASES = [
    # ── Basic retrieval ──────────────────────────────────────────────────
    {
        "id": "results_winner",
        "question": "Who won the race?",
        "expected_tools": ["race_result"],
        "keywords": ["p1", "1", "won", "first", "winner", "victory"],
        "page": "general",
    },
    {
        "id": "results_podium",
        "question": "What was the podium?",
        "expected_tools": ["race_result"],
        "keywords": ["p1", "p2", "p3", "1", "2", "3", "podium"],
        "page": "general",
    },
    {
        "id": "session_overview",
        "question": "Give me a quick overview of this session",
        "expected_tools": ["session_summary"],
        "keywords": ["lap", "winner", "pit"],
        "page": "general",
    },
    {
        "id": "drivers_list",
        "question": "Who was in this race?",
        "expected_tools": ["list_drivers"],
        "keywords": ["ver", "ham", "lec"],
        "page": "general",
    },
    # ── Fuzzy driver resolution ──────────────────────────────────────────
    {
        "id": "fuzzy_first_name",
        "question": "How did Charles do?",
        "expected_tools": ["lap_times", "race_result"],
        "keywords": ["lec", "leclerc", "charles"],
        "page": "general",
    },
    {
        "id": "fuzzy_nickname",
        "question": "What was Checo's strategy?",
        "expected_tools": ["pit_stops", "tire_stints"],
        "keywords": ["per", "perez", "checo"],
        "page": "general",
    },
    {
        "id": "fuzzy_number",
        "question": "How fast was car 44?",
        "expected_tools": ["driver_telemetry", "lap_times"],
        "keywords": ["ham", "hamilton", "speed", "km/h"],
        "page": "general",
    },
    # ── Strategy questions ───────────────────────────────────────────────
    {
        "id": "pit_strategy_all",
        "question": "When did everyone pit?",
        "expected_tools": ["pit_stops"],
        "keywords": ["lap", "stop", "pit"],
        "page": "pitstrategy",
    },
    {
        "id": "tyre_usage",
        "question": "What tyres did the top 3 use?",
        "expected_tools": ["tire_stints"],
        "keywords": ["soft", "medium", "hard"],
        "page": "pitstrategy",
    },
    {
        "id": "pit_specific_driver",
        "question": "Why did Sainz pit when he did?",
        "expected_tools": ["pit_stops", "lap_times", "tire_stints"],
        "keywords": ["sai", "sainz", "pit", "lap"],
        "page": "pitstrategy",
    },
    # ── Telemetry questions ──────────────────────────────────────────────
    {
        "id": "top_speed",
        "question": "What was Verstappen's top speed?",
        "expected_tools": ["driver_telemetry"],
        "keywords": ["speed", "km/h", "ver", "verstappen"],
        "page": "telemetry",
    },
    {
        "id": "braking_comparison",
        "question": "Who brakes harder, Norris or Piastri?",
        "expected_tools": ["driver_telemetry", "head_to_head"],
        "keywords": ["brak", "nor", "pia"],
        "page": "telemetry",
    },
    # ── Comparison questions ─────────────────────────────────────────────
    {
        "id": "head_to_head",
        "question": "Compare Verstappen and Leclerc",
        "expected_tools": ["head_to_head"],
        "keywords": ["ver", "lec", "position", "pace"],
        "page": "general",
    },
    {
        "id": "fastest_lap_ranking",
        "question": "Who set the fastest lap?",
        "expected_tools": ["fastest_laps"],
        "keywords": ["fastest", "lap", "time"],
        "page": "general",
    },
    # ── Conditions ───────────────────────────────────────────────────────
    {
        "id": "weather",
        "question": "What was the weather like?",
        "expected_tools": ["weather"],
        "keywords": ["temp", "track", "humidity", "°"],
        "page": "general",
    },
    # ── Advanced analysis ────────────────────────────────────────────────
    {
        "id": "energy_clipping",
        "question": "Where was Verstappen power-limited?",
        "expected_tools": ["energy_analysis"],
        "keywords": ["ver", "energy", "clip", "battery", "mgu", "deploy"],
        "page": "energy",
    },
    {
        "id": "overtake_chances",
        "question": "Who was most likely to overtake?",
        "expected_tools": ["overtake_probability"],
        "keywords": ["overtake", "gap", "probability", "pace"],
        "page": "general",
    },
    {
        "id": "track_rubber",
        "question": "Did the track get faster over the race?",
        "expected_tools": ["track_evolution"],
        "keywords": ["track", "pace", "grip", "early", "late"],
        "page": "general",
    },
    {
        "id": "tyre_predictions",
        "question": "Who needs to pit next based on tyre life?",
        "expected_tools": ["tyre_predictions"],
        "keywords": ["tyre", "tire", "pit", "life", "degrad"],
        "page": "performance",
    },
    {
        "id": "key_moments",
        "question": "What were the key moments of the race?",
        "expected_tools": ["session_insights"],
        "keywords": ["lap", "overtake", "pit", "safety", "strategy"],
        "page": "general",
    },
    # ── Multi-turn conversation ──────────────────────────────────────────
    {
        "id": "multi_turn_setup",
        "question": "How did Hamilton do?",
        "expected_tools": ["lap_times", "race_result"],
        "keywords": ["ham", "hamilton"],
        "page": "general",
        "follow_up": {
            "question": "And how does that compare to his teammate?",
            "expected_tools": ["head_to_head"],
            "keywords": ["russell", "rus", "ham", "teammate"],
        },
    },
]


# ── Scoring ──────────────────────────────────────────────────────────────────


def score_tool_accuracy(expected: list[str], actual: list[dict]) -> dict:
    """Score how well Claude picked the right tools."""
    actual_names = [t["tool"] for t in actual]
    actual_set = set(actual_names)
    expected_set = set(expected)

    # Did it call at least one expected tool?
    hits = expected_set & actual_set
    misses = expected_set - actual_set
    extras = actual_set - expected_set

    # Flexible scoring: at least one expected tool = pass
    any_hit = len(hits) > 0
    # Strict scoring: all expected tools called
    all_hit = len(misses) == 0

    return {
        "expected": sorted(expected),
        "actual": sorted(actual_names),
        "hits": sorted(hits),
        "misses": sorted(misses),
        "extras": sorted(extras),
        "any_expected_called": any_hit,
        "all_expected_called": all_hit,
        "used_tools": len(actual_names) > 0,
        "score": len(hits) / len(expected_set) if expected_set else 1.0,
    }


def score_content_relevance(keywords: list[str], reply: str) -> dict:
    """Check if the response mentions expected keywords."""
    reply_lower = reply.lower()
    found = [kw for kw in keywords if kw.lower() in reply_lower]
    missed = [kw for kw in keywords if kw.lower() not in reply_lower]

    return {
        "keywords_expected": keywords,
        "keywords_found": found,
        "keywords_missed": missed,
        "score": len(found) / len(keywords) if keywords else 1.0,
    }


# ── Runner ───────────────────────────────────────────────────────────────────


def run_single(client: httpx.Client, api_key: str, case: dict, history: list = None) -> dict:
    """Run a single test case and return full results."""
    question = case["question"]
    page = case.get("page", "general")

    start = time.time()
    try:
        resp = client.post(
            "/api/session/chat",
            json={
                "apiKey": api_key,
                "question": question,
                "page": page,
                "history": history or [],
            },
            timeout=60,
        )
        latency = round(time.time() - start, 2)

        if resp.status_code != 200:
            return {
                "id": case["id"],
                "question": question,
                "status": "error",
                "error": resp.text,
                "latency_s": latency,
            }

        data = resp.json()
        reply = data.get("reply", "")
        tools_called = data.get("tools_called", [])
        usage = data.get("usage", {})

        tool_score = score_tool_accuracy(case["expected_tools"], tools_called)
        content_score = score_content_relevance(case.get("keywords", []), reply)

        return {
            "id": case["id"],
            "question": question,
            "page": page,
            "status": "ok",
            "reply": reply,
            "tools_called": tools_called,
            "tool_score": tool_score,
            "content_score": content_score,
            "usage": usage,
            "latency_s": latency,
        }

    except Exception as e:
        return {
            "id": case["id"],
            "question": question,
            "status": "exception",
            "error": str(e),
            "latency_s": round(time.time() - start, 2),
        }


def run_eval(base_url: str, api_key: str) -> dict:
    """Run all test cases and return the full eval report."""
    client = httpx.Client(base_url=base_url)

    # Check session is loaded
    status = client.get("/api/session/status").json()
    if not status.get("loaded"):
        print("ERROR: No session loaded. Load a session first via the UI.")
        return {}

    print(f"Session: {status.get('year')} {status.get('event')} ({status.get('session')})")
    print(f"Running {len(TEST_CASES)} test cases...\n")

    results = []
    for i, case in enumerate(TEST_CASES):
        print(f"[{i+1}/{len(TEST_CASES)}] {case['id']}: {case['question']}")
        result = run_single(client, api_key, case)

        if result["status"] == "ok":
            tool_pct = int(result["tool_score"]["score"] * 100)
            content_pct = int(result["content_score"]["score"] * 100)
            tools = [t["tool"] for t in result["tools_called"]]
            tokens = result["usage"].get("input_tokens", 0) + result["usage"].get("output_tokens", 0)
            print(f"  Tools: {tools}")
            print(f"  Score: tool={tool_pct}% content={content_pct}% | {tokens} tokens | {result['latency_s']}s")
        else:
            print(f"  FAILED: {result.get('error', 'unknown')[:80]}")

        results.append(result)

        # Handle follow-up if present
        if case.get("follow_up") and result["status"] == "ok":
            follow = case["follow_up"]
            follow_case = {
                "id": f"{case['id']}_followup",
                "question": follow["question"],
                "expected_tools": follow["expected_tools"],
                "keywords": follow.get("keywords", []),
                "page": case.get("page", "general"),
            }
            # Build conversation history
            history = [
                {"role": "user", "content": case["question"]},
                {"role": "assistant", "content": result["reply"]},
            ]
            print(f"  Follow-up: {follow['question']}")
            follow_result = run_single(client, api_key, follow_case, history=history)

            if follow_result["status"] == "ok":
                tool_pct = int(follow_result["tool_score"]["score"] * 100)
                content_pct = int(follow_result["content_score"]["score"] * 100)
                tools = [t["tool"] for t in follow_result["tools_called"]]
                print(f"  Follow-up tools: {tools}")
                print(f"  Follow-up score: tool={tool_pct}% content={content_pct}%")

            results.append(follow_result)

        print()

    client.close()

    # ── Summary ──────────────────────────────────────────────────────────
    ok_results = [r for r in results if r["status"] == "ok"]
    failed = [r for r in results if r["status"] != "ok"]

    total_tool_score = sum(r["tool_score"]["score"] for r in ok_results) / len(ok_results) if ok_results else 0
    total_content_score = sum(r["content_score"]["score"] for r in ok_results) / len(ok_results) if ok_results else 0
    total_tokens = sum(
        r["usage"].get("input_tokens", 0) + r["usage"].get("output_tokens", 0)
        for r in ok_results
    )
    avg_latency = sum(r["latency_s"] for r in ok_results) / len(ok_results) if ok_results else 0
    used_tools_pct = sum(1 for r in ok_results if r["tool_score"]["used_tools"]) / len(ok_results) * 100 if ok_results else 0

    summary = {
        "total_cases": len(results),
        "passed": len(ok_results),
        "failed": len(failed),
        "tool_accuracy": round(total_tool_score * 100, 1),
        "content_relevance": round(total_content_score * 100, 1),
        "used_tools_pct": round(used_tools_pct, 1),
        "total_tokens": total_tokens,
        "avg_latency_s": round(avg_latency, 2),
        "avg_tokens_per_question": round(total_tokens / len(ok_results), 0) if ok_results else 0,
    }

    report = {
        "timestamp": datetime.now().isoformat(),
        "session": status,
        "summary": summary,
        "results": results,
    }

    # ── Print summary ────────────────────────────────────────────────────
    print("=" * 60)
    print("EVAL SUMMARY")
    print("=" * 60)
    print(f"  Cases:              {summary['total_cases']} ({summary['passed']} passed, {summary['failed']} failed)")
    print(f"  Tool accuracy:      {summary['tool_accuracy']}%")
    print(f"  Content relevance:  {summary['content_relevance']}%")
    print(f"  Used tools:         {summary['used_tools_pct']}% of responses")
    print(f"  Total tokens:       {summary['total_tokens']:,}")
    print(f"  Avg tokens/question:{summary['avg_tokens_per_question']:,.0f}")
    print(f"  Avg latency:        {summary['avg_latency_s']}s")
    print()

    if failed:
        print("FAILURES:")
        for r in failed:
            print(f"  {r['id']}: {r.get('error', 'unknown')[:80]}")
        print()

    # ── Worst scoring cases ──────────────────────────────────────────────
    low_tool = [r for r in ok_results if r["tool_score"]["score"] < 0.5]
    if low_tool:
        print("LOW TOOL ACCURACY (<50%):")
        for r in low_tool:
            print(f"  {r['id']}: expected {r['tool_score']['expected']}, got {r['tool_score']['actual']}")
        print()

    no_tools = [r for r in ok_results if not r["tool_score"]["used_tools"]]
    if no_tools:
        print("NO TOOLS CALLED (answered without data):")
        for r in no_tools:
            print(f"  {r['id']}: {r['question']}")
        print()

    return report


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="F1 AI Chat Eval")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend URL")
    parser.add_argument("--key", default=None, help="Anthropic API key (or set ANTHROPIC_API_KEY)")
    args = parser.parse_args()

    api_key = args.key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Set ANTHROPIC_API_KEY env var or pass --key")
        return

    report = run_eval(args.url, api_key)
    if not report:
        return

    # Save results
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"eval_{timestamp}.json"
    out_file.write_text(json.dumps(report, indent=2, default=str))
    print(f"Results saved to: {out_file}")


if __name__ == "__main__":
    main()
