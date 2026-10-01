"""The shared YAML profile: YAML 1.1 as PyYAML's safe loader reads it (last duplicate key wins)."""

from __future__ import annotations

from typing import Any

import yaml

YAMLError = yaml.YAMLError


def load_yaml(text: str) -> Any:
    return yaml.safe_load(text)
