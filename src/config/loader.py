from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
import os


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_CONFIG_PATH = PROJECT_ROOT / "config" / "campana.yaml"
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH)


def load_campaign_config() -> dict[str, Any]:
    with CAMPAIGN_CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_openai_config() -> dict[str, str]:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("MODELO")

    if not api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")

    if not model:
        raise ValueError("MODELO is not configured.")

    return {
        "api_key": api_key,
        "model": model,
    }