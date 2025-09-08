# settings.py
import os
import json

APP_NAME = "descanso_visual"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "work_minutes": 20,
    "rest_minutes": 10,
    "show_notifications": True,
    "always_on_top": True,
}


def ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_config():
    ensure_config_dir()
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULTS.copy())
        return DEFAULTS.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = DEFAULTS.copy()
        if isinstance(data, dict):
            cfg.update(data)
        # sane bounds (asegurar ints)
        try:
            cfg["work_minutes"] = int(max(1, min(int(cfg.get("work_minutes", 20)), 240)))
        except Exception:
            cfg["work_minutes"] = DEFAULTS["work_minutes"]
        try:
            cfg["rest_minutes"] = int(max(1, min(int(cfg.get("rest_minutes", 10)), 120)))
        except Exception:
            cfg["rest_minutes"] = DEFAULTS["rest_minutes"]
        cfg["show_notifications"] = bool(cfg.get("show_notifications", True))
        cfg["always_on_top"] = bool(cfg.get("always_on_top", True))
        return cfg
    except Exception:
        return DEFAULTS.copy()


def save_config(cfg):
    ensure_config_dir()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
