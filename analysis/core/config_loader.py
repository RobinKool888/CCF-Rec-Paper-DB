import yaml
import os


REQUIRED_FIELDS = [
    ["paths", "paper_db"],
    ["paths", "ccf_catalog"],
    ["paths", "cache_dir"],
    ["llm", "provider"],
    ["llm", "model"],
]


def load_config(config_path: str) -> dict:
    """Read YAML config, validate required fields, return dict."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict):
        raise ValueError("Config must be a YAML mapping")
    for path in REQUIRED_FIELDS:
        node = cfg
        for key in path:
            if not isinstance(node, dict) or key not in node:
                raise ValueError(
                    f"Config missing required field: {'.'.join(path)}"
                )
            node = node[key]
    return cfg
