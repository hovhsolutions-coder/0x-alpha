import os
import json
from pathlib import Path

# Application Metadata
APP_NAME = "0x Alpha Workspace"
APP_VERSION = "1.0.0-preview"

# Default Model & Provider Configuration
DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1"
STEALTH_MODEL_ID = "0x-alpha"  # Target stealth model identifier on OpenRouter / OpenCode Zen
MAX_CONTEXT_TOKENS = 1_050_000
MAX_OUTPUT_TOKENS = 131_072

# System Paths
APP_DATA_DIR = Path.home() / ".0x_alpha"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = APP_DATA_DIR / "workspace.db"
CONFIG_FILE = APP_DATA_DIR / "config.json"


class ConfigManager:
    """Manages application settings and API key persistence."""

    def __init__(self):
        self.config_path = CONFIG_FILE
        self.settings = self._load_defaults()
        self.load()

    def _load_defaults(self) -> dict:
        return {
            "api_key": os.getenv("OPENROUTER_API_KEY", ""),
            "api_base": DEFAULT_OPENROUTER_URL,
            "model": STEALTH_MODEL_ID,
            "temperature": 0.2,
            "max_tokens": 16384,
            "dark_mode": True,
        }

    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.settings.update(data)
            except Exception as e:
                print(f"Error loading settings: {e}")

    def save(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get(self, key: str, default=None):
        return self.settings.get(key, default)

    def set(self, key: str, value):
        self.settings[key] = value
        self.save()
