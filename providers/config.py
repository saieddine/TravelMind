"""Shared-root resources and private environment path; no credential logging."""
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = PROJECT_ROOT / "data" / "sasha"
def environment_file():
    return PROJECT_ROOT / ".env"
