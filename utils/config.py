import os, yaml
from pathlib import Path


def load_config(path_env="APP_CONFIG_FILE") -> dict:
    path = Path(os.getenv(path_env, "./config/app.yaml"))
    if not path.exists():
        raise FileNotFoundError(f"Config file non trovato: {path}")

    if path.suffix in {".yaml", ".yml"}:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    elif path.suffix == ".toml":
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    elif path.suffix == ".json":
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        raise ValueError(f"Formato non supportato: {path.suffix}")

    return data
