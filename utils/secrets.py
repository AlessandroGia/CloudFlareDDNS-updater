import os
from pathlib import Path

def get_secret(name: str, default: str | None = None) -> str:
    """
    Read <Name>_FILE (path to secret file) first,
    then <NAME> (direct value).
    If not found, use default or raise error.
    """
    file_var = os.getenv(f"{name}_FILE")
    if file_var and Path(file_var).exists():
        try:
            return Path(file_var).read_text(encoding="utf-8").strip()
        except Exception as e:
            raise RuntimeError(f"Error reading secret file '{file_var}': {e}")
    val = os.getenv(name)
    if val is not None:
        return val.strip()
    if default is not None:
        return default
    raise RuntimeError(f"Secret '{name}' not found in environment {name} or file '{file_var}'")
