"""Import only the explicitly authorized model service into the ignored local .env."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values, set_key

from backend.app.config import ROOT

PRICING_URL = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    values = dotenv_values(source / ".env", encoding="utf-8-sig")
    model = values.get("DEEPSEEK_MODEL") or "deepseek-flash"
    endpoint = values.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
    data = Path(values.get("QINGGUI_DATA_DIR") or source / "data")
    override = data / "dashboard/model-config.json"
    if override.is_file():
        saved = json.loads(override.read_text(encoding="utf-8"))
        model = saved.get("model") or model
        endpoint = saved.get("base_url") or endpoint
    key = values.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("The authorized configuration has no model credential; no values copied")
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or parsed.hostname != "api.deepseek.com" or parsed.username or parsed.password or parsed.query:
        raise ValueError("Nonstandard provider: its current pricing must be verified before import")
    if model in {"deepseek-flash", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"}:
        input_price, output_price = 2, 8
    elif model == "deepseek-v4-pro":
        input_price, output_price = 9, 27
    else:
        raise ValueError("Unknown model pricing: no paid configuration imported")
    destination = ROOT / ".env"
    if not destination.exists():
        destination.write_text((ROOT / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
    for name, value in {
        "MODEL_MODE": "live", "MODEL_BASE_URL": endpoint, "MODEL_ID": model,
        "MODEL_API_KEY": key, "MODEL_INPUT_CNY_PER_MILLION": str(input_price),
        "MODEL_OUTPUT_CNY_PER_MILLION": str(output_price),
    }.items():
        set_key(destination, name, value)
    record = {"source": str(source), "credential_copied": True, "secret_displayed": False,
              "model_id": model, "provider_host": parsed.hostname,
              "input_cny_per_million": input_price, "output_cny_per_million": output_price,
              "cost_policy": "Conservative peak/cache-miss prices; actual provider bill may be lower",
              "pricing_verified_date": "2026-11-10", "pricing_source": PRICING_URL,
              "scope": "Only model parameters; no QQ identifiers, private memories or user preferences imported"}
    evidence = ROOT / "docs/evidence/model-configuration-20261110.json"
    evidence.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"model_id": model, "provider_host": parsed.hostname, "credential_present": True}))


if __name__ == "__main__":
    main()
