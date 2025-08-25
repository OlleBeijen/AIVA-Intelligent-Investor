from datetime import datetime
import pytz
from pathlib import Path
import yaml

def now_ams() -> str:
    tz = pytz.timezone("Europe/Amsterdam")
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M")

def resolve_config(config_path: str = "config.yaml") -> Path:
    cand = Path(config_path)
    if cand.is_file(): return cand
    cwd = Path.cwd() / config_path
    if cwd.is_file(): return cwd
    repo_root = Path(__file__).resolve().parents[1] / config_path
    if repo_root.is_file(): return repo_root
    repo_root2 = Path(__file__).resolve().parents[2] / config_path if len(Path(__file__).resolve().parents) > 2 else None
    if repo_root2 and repo_root2.is_file(): return repo_root2
    raise FileNotFoundError("config.yaml niet gevonden.")

def load_config(config_path: str = "config.yaml") -> dict:
    p = resolve_config(config_path)
    return yaml.safe_load(p.read_text(encoding="utf-8"))

def save_config(cfg: dict, config_path: str = "config.yaml") -> Path:
    p = resolve_config(config_path) if Path(config_path).exists() else Path(config_path)
    p.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return p
