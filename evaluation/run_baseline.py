"""Opt-in, capped collection of the current single-VLM image baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from pathlib import Path

from evaluation.registry import load_registry

PIPELINE_VERSION = "single_vlm_screening_v1"


def run_pilot(
    manifest: Path,
    data_root: Path,
    output: Path,
    *,
    model_id: str,
    max_calls: int,
    max_observed_cost_usd: float,
    account_hard_cap_confirmed: bool = False,
) -> int:
    """Collect pilot observations; account-level hard cap is required separately."""
    from backend import qwen_agent

    if not account_hard_cap_confirmed:
        raise ValueError("Provider account hard cap must be confirmed before paid calls")
    if max_calls < 1 or not math.isfinite(max_observed_cost_usd) or max_observed_cost_usd <= 0:
        raise ValueError("Positive --max-calls and --max-observed-cost-usd are required")
    if output.exists():
        raise ValueError("Output already exists; use a new run file to preserve provenance")
    if model_id not in qwen_agent.ALLOWED_VISION_MODELS:
        raise ValueError("Model is not on the approved vision allowlist")
    if not qwen_agent.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not configured locally")
    items = load_registry(manifest, data_root)
    pilot = [
        item for item in items
        if item.split == "pilot" and item.media_type == "image"
        and item.label in {"authentic", "fully_generated"}
    ]
    if not pilot:
        raise ValueError("No pilot images with authentic/fully_generated labels")
    qwen_agent.VISION_MODEL_ID = model_id
    registry_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    code_sha256 = hashlib.sha256(Path(qwen_agent.__file__).read_bytes()).hexdigest()
    prompt_sha256 = hashlib.sha256(qwen_agent._SYSTEM_PROMPT.encode()).hexdigest()
    observed_cost = 0.0
    completed = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        for item in pilot[:max_calls]:
            # The provider account's hard cap is the only reliable pre-call money limit.
            if observed_cost >= max_observed_cost_usd:
                break
            started = time.perf_counter()
            record = {
                "item_id": item.item_id,
                "sha256": item.sha256,
                "model_id": model_id,
                "pipeline_version": PIPELINE_VERSION,
                "registry_sha256": registry_sha256,
                "code_sha256": code_sha256,
                "prompt_sha256": prompt_sha256,
                "status": "error",
                "classification": None,
                "model_confidence": None,
                "usage": {},
                "latency_ms": None,
            }
            try:
                result = qwen_agent.analyze_media(
                    str((data_root / item.relative_path).resolve()), "image/jpeg", "Image"
                )
                usage = result.get("model_usage") or {}
                cost = usage.get("cost")
                if (
                    not isinstance(cost, (int, float)) or isinstance(cost, bool)
                    or not math.isfinite(cost) or cost < 0
                ):
                    record["status"] = "unpriced"
                else:
                    observed_cost += float(cost)
                    record["status"] = "ok"
                record["classification"] = result["classification"]
                record["model_confidence"] = result["confidence_score"]
                record["usage"] = usage
            except Exception as error:
                # Keep the paid call count and failure type; never print original evidence.
                record["error_type"] = type(error).__name__
            record["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            completed += 1
            if record["status"] != "ok":
                break
    return completed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--max-calls", type=int, required=True)
    parser.add_argument("--max-observed-cost-usd", type=float, required=True)
    parser.add_argument(
        "--account-hard-cap-confirmed", action="store_true",
        help="Confirm a separate provider account/key hard cap is active before paid calls",
    )
    args = parser.parse_args()
    if not args.account_hard_cap_confirmed:
        parser.error("Provider account hard cap must be confirmed before paid calls")
    count = run_pilot(
        args.manifest, args.data_root, args.output, model_id=args.model_id,
        max_calls=args.max_calls, max_observed_cost_usd=args.max_observed_cost_usd,
        account_hard_cap_confirmed=args.account_hard_cap_confirmed,
    )
    print(json.dumps({"attempted_calls": count, "output": os.fspath(args.output)}))


if __name__ == "__main__":
    main()
