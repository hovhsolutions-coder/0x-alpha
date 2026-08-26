import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from config import DB_PATH


class StorageManager:
    """Handles local storage for chats, projects, and message history using SQLite.

    Includes export/import so chats can be synced between devices
    without requiring a cloud backend (portable JSON snapshot).
    """

    EXPORT_FORMAT_VERSION = 1

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates tables for sessions and messages if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Chat sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    workspace_path TEXT
                )
            """)
            
            # Messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    attachments_json TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def create_session(self, session_id: str, title: str, workspace_path: Optional[str] = None):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO sessions (id, title, workspace_path) VALUES (?, ?, ?)",
                (session_id, title, workspace_path)
            )
            conn.commit()

    def get_sessions(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def add_message(self, session_id: str, role: str, content: str, attachments: Optional[List[dict]] = None):
        attachments_str = json.dumps(attachments) if attachments else None
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, attachments_json) VALUES (?, ?, ?, ?)",
                (session_id, role, content, attachments_str)
            )
            conn.commit()

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT role, content, attachments_json FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,)
            )
            results = []
            for row in cursor.fetchall():
                item = dict(row)
                if item["attachments_json"]:
                    item["attachments"] = json.loads(item["attachments_json"])
                else:
                    item["attachments"] = []
                del item["attachments_json"]
                results.append(item)
            return results

    def delete_session(self, session_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()

    # ------------------------------------------------------------------
    # Device-to-device sync (export / import)
    # ------------------------------------------------------------------

    def export_all(self) -> Dict[str, Any]:
        """Serializes every session and its messages into a portable dict.

        The result is safe to write to disk as JSON and can be imported
        on another device running this app.
        """
        export: Dict[str, Any] = {
            "app": "0x-alpha",
            "kind": "chat-export",
            "version": self.EXPORT_FORMAT_VERSION,
            "sessions": [],
        }
        for sess in self.get_sessions():
            export["sessions"].append({
                "id": sess["id"],
                "title": sess["title"],
                "created_at": sess["created_at"],
                "workspace_path": sess.get("workspace_path"),
                "messages": self.get_messages(sess["id"]),
            })
        return export

    def import_data(self, data: Dict[str, Any]) -> Tuple[int, int]:
        """Merges an exported snapshot into the local database.

        Idempotent: sessions whose id already exists locally are kept as-is
        (no duplicates), and per-session messages are de-duplicated on
        (role, content). Safe to run the same import twice.

        Returns a tuple of (added_sessions, added_messages).
        """
        if not isinstance(data, dict) or data.get("kind") != "chat-export":
            raise ValueError("Not a valid 0x Alpha chat export")

        added_sessions = 0
        added_messages = 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            existing_ids = {
                row["id"] for row in cursor.execute("SELECT id FROM sessions").fetchall()
            }

            for sess in data.get("sessions", []):
                sid = sess["id"]
                if sid not in existing_ids:
                    cursor.execute(
                        "INSERT INTO sessions (id, title, created_at, workspace_path) VALUES (?, ?, ?, ?)",
                        (
                            sid,
                            sess.get("title") or "Imported chat",
                            sess.get("created_at"),
                            sess.get("workspace_path"),
                        ),
                    )
                    existing_ids.add(sid)
                    added_sessions += 1

                existing_msgs = {
                    (row["role"], row["content"])
                    for row in cursor.execute(
                        "SELECT role, content FROM messages WHERE session_id = ?", (sid,)
                    ).fetchall()
                }

                for msg in sess.get("messages", []):
                    key = (msg.get("role", "user"), msg.get("content", ""))
                    if key in existing_msgs:
                        continue
                    attachments = msg.get("attachments") or None
                    cursor.execute(
                        "INSERT INTO messages (session_id, role, content, attachments_json) VALUES (?, ?, ?, ?)",
                        (
                            sid,
                            key[0],
                            key[1],
                            json.dumps(attachments) if attachments else None,
                        ),
                    )
                    existing_msgs.add(key)
                    added_messages += 1

            conn.commit()

        return added_sessions, added_messages
