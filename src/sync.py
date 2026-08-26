"""Chat synchronization across devices via a private GitHub Gist backend.

All chats are stored locally in SQLite (per device). This module adds an
opt-in sync layer: the full local chat dump (sessions + messages) is pushed
to a private Gist owned by the user, and pulled/merged at startup.

Settings are stored through ConfigManager under the keys:
  - sync_github_token : personal access token (gist scope)
  - sync_gist_id      : id of the private gist containing chats.json
"""

import json
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

GIST_API_URL = "https://api.github.com/gists"
SYNC_FILENAME = "chats.json"


class GistSync:
    """Push/pull the local chat database to a private GitHub Gist."""

    def __init__(self, get_setting, export_all, import_all):
        """
        get_setting : callable(key, default) -> value  (ConfigManager.get)
        export_all  : callable() -> dict               (StorageManager.export_all)
        import_all  : callable(data) -> None           (StorageManager.import_all)
        """
        self._get = get_setting
        self._export_all = export_all
        self._import_all = import_all

    @property
    def is_configured(self) -> bool:
        return bool(self._get("sync_github_token", "") and self._get("sync_gist_id", ""))

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get('sync_github_token', '')}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "0x-alpha-desktop-client",
        }

    def _request(self, method: str, url: str, body: Optional[dict] = None) -> Optional[dict]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"GistSync HTTP error {e.code}: {e.reason}")
            return None
        except Exception as e:
            print(f"GistSync request failed: {e}")
            return None

    def pull(self, overwrite_remote: bool = False) -> bool:
        """Fetch remote chats.json and merge into local DB. Returns success."""
        if not self.is_configured:
            return False
        payload = self._request(
            "GET", f"{GIST_API_URL}/{self._get('sync_gist_id', '')}"
        )
        if not payload:
            return False
        raw = payload.get("files", {}).get(SYNC_FILENAME, {}).get("content")
        if not raw:
            return False
        try:
            data = json.loads(raw)
            self._import_all(data)
            return True
        except Exception as e:
            print(f"GistSync failed to parse remote chats: {e}")
            return False

    def push(self) -> bool:
        """Upload the full local chat dump to the gist. Returns success."""
        if not self.is_configured:
            return False
        try:
            dump = self._export_all()
        except Exception as e:
            print(f"GistSync local export failed: {e}")
            return False
        result = self._request(
            "PATCH",
            f"{GIST_API_URL}/{self._get('sync_gist_id', '')}",
            {"files": {SYNC_FILENAME: {"content": json.dumps(dump)}}},
        )
        return result is not None

    def create_sync_gist(self) -> Optional[str]:
        """One-time helper: create the private gist and return its id."""
        if not self._get("sync_github_token", ""):
            return None
        payload = {
            "description": "0x Alpha desktop client — chat sync (private)",
            "public": False,
            "files": {SYNC_FILENAME: {"content": json.dumps({"sessions": [], "messages": []})}},
        }
        result = self._request("POST", GIST_API_URL, payload)
        return result.get("id") if result else None
