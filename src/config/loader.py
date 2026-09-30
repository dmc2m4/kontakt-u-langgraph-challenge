from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_CONFIG_PATH = PROJECT_ROOT / "config" / "campana.yaml"


def load_campaign_config() -> dict[str, Any]:
    with CAMPAIGN_CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)