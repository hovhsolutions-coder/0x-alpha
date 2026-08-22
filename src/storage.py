import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import DB_PATH


class StorageManager:
    """Handles local storage for chats, projects, and message history using SQLite."""

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
