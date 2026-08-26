import uuid
import os
import json
from datetime import datetime
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
    QTextEdit, QPushButton, QFileDialog, QLabel, QLineEdit,
    QSplitter, QCheckBox, QMessageBox, QListWidgetItem
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont

from config import ConfigManager, STEALTH_MODEL_ID
from storage import StorageManager
from workspace import WorkspaceManager
from api_client import OpenRouterClient, CompletionWorker


class MainWindow(QMainWindow):
    """Main Application Window for 0x Alpha Desktop Client."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("0x Alpha — Stealth Model Desktop Client")
        self.resize(1280, 800)

        # Initialize Managers
        self.config = ConfigManager()
        self.storage = StorageManager()
        self.workspace = WorkspaceManager()

        self.current_session_id = None
        self.attached_images = []
        self.active_worker = None

        self._init_ui()
        self._apply_dark_theme()
        self.load_sessions()

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Main horizontal splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left Sidebar (Sessions & Workspace Setup)
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)

        sidebar_layout.addWidget(QLabel("<b>0x Alpha Workspace</b>"))

        # API Key input
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter OpenRouter API Key...")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setText(self.config.get("api_key", ""))
        self.api_key_input.textChanged.connect(self._on_api_key_changed)
        sidebar_layout.addWidget(self.api_key_input)

        # New Chat Button
        new_chat_btn = QPushButton("+ New Chat")
        new_chat_btn.clicked.connect(self.create_new_session)
        sidebar_layout.addWidget(new_chat_btn)

        # Chat Sync Buttons (Export / Import)
        sync_layout = QHBoxLayout()
        self.btn_export_chats = QPushButton("\u2b06 Export")
        self.btn_export_chats.setToolTip("Export all chats to a portable JSON file")
        self.btn_export_chats.clicked.connect(self.export_chats)
        sync_layout.addWidget(self.btn_export_chats)

        self.btn_import_chats = QPushButton("\u2b07 Import")
        self.btn_import_chats.setToolTip("Merge chats from an exported JSON file (no duplicates)")
        self.btn_import_chats.clicked.connect(self.import_chats)
        sync_layout.addWidget(self.btn_import_chats)
        sidebar_layout.addLayout(sync_layout)

        # Sessions List
        sidebar_layout.addWidget(QLabel("Recent Chats:"))
        self.session_list_widget = QListWidget()
        self.session_list_widget.itemClicked.connect(self._on_session_selected)
        sidebar_layout.addWidget(self.session_list_widget)

        # Workspace Directory Picker
        sidebar_layout.addWidget(QLabel("Codebase Workspace:"))
        self.btn_select_workspace = QPushButton("Open Folder...")
        self.btn_select_workspace.clicked.connect(self.select_workspace)
        sidebar_layout.addWidget(self.btn_select_workspace)

        self.lbl_workspace_path = QLabel("No workspace loaded")
        self.lbl_workspace_path.setStyleSheet("color: #888; font-size: 11px;")
        sidebar_layout.addWidget(self.lbl_workspace_path)

        sidebar.setFixedWidth(280)
        splitter.addWidget(sidebar)

        # Right Panel (Chat and Code Interaction)
        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)

        # Conversation History Area
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setFont(QFont("Consolas", 10))
        chat_layout.addWidget(self.chat_display)

        # Attachments Status Label
        self.lbl_attachments = QLabel("")
        self.lbl_attachments.setStyleSheet("color: #0EA5E9;")
        chat_layout.addWidget(self.lbl_attachments)

        # Workspace context toggle checkbox
        self.chk_include_context = QCheckBox("Include Entire Project Codebase in Context (1.05M Token Limit)")
        chat_layout.addWidget(self.chk_include_context)

        # Input Area Controls
        input_controls_layout = QHBoxLayout()

        self.input_text = QTextEdit()
        self.input_text.setMaximumHeight(100)
        self.input_text.setPlaceholderText("Ask 0x Alpha to refactor, write, or explain code...")
        input_controls_layout.addWidget(self.input_text)

        action_btn_layout = QVBoxLayout()
        self.btn_attach_image = QPushButton("📷 Image")
        self.btn_attach_image.clicked.connect(self.attach_image)
        action_btn_layout.addWidget(self.btn_attach_image)

        self.btn_send = QPushButton("Send")
        self.btn_send.clicked.connect(self.send_message)
        action_btn_layout.addWidget(self.btn_send)

        input_controls_layout.addLayout(action_btn_layout)
        chat_layout.addLayout(input_controls_layout)

        splitter.addWidget(chat_container)
        main_layout.addWidget(splitter)

    def _apply_dark_theme(self):
        """Applies a modern dark stylesheet matching the repository badges theme."""
        dark_stylesheet = """
            QMainWindow, QWidget {
                background-color: #111827;
                color: #F3F4F6;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QTextEdit, QLineEdit, QListWidget {
                background-color: #1F2937;
                color: #F9FAFB;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 6px;
            }
            QPushButton {
                background-color: #0EA5E9;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 8px 14px;
            }
            QPushButton:hover {
                background-color: #0284C7;
            }
            QCheckBox {
                color: #9CA3AF;
            }
            QSplitter::handle {
                background-color: #374151;
            }
        """
        self.setStyleSheet(dark_stylesheet)

    def _on_api_key_changed(self, text: str):
        self.config.set("api_key", text.strip())

    def load_sessions(self):
        self.session_list_widget.clear()
        sessions = self.storage.get_sessions()
        for sess in sessions:
            item = QListWidgetItem(sess["title"])
            item.setData(Qt.UserRole, sess["id"])
            self.session_list_widget.addItem(item)

        if not sessions:
            self.create_new_session()

    def create_new_session(self):
        session_id = str(uuid.uuid4())
        title = f"Session {session_id[:6]}"
        ws_path = str(self.workspace.root_dir) if self.workspace.root_dir else None

        self.storage.create_session(session_id, title, ws_path)
        self.current_session_id = session_id
        self.chat_display.clear()
        self.load_sessions()

    def select_workspace(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Project Folder")
        if directory:
            self.workspace.set_root(directory)
            self.lbl_workspace_path.setText(f"Active: {os.path.basename(directory)}")

    def attach_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.jpg *.jpeg)")
        if file_path:
            self.attached_images.append(file_path)
            self.lbl_attachments.setText(f"Attached Images: {len(self.attached_images)}")

    def _on_session_selected(self, item: QListWidgetItem):
        session_id = item.data(Qt.UserRole)
        self.current_session_id = session_id
        self.reload_chat_history()

    def reload_chat_history(self):
        self.chat_display.clear()
        messages = self.storage.get_messages(self.current_session_id)
        for msg in messages:
            role = "User" if msg["role"] == "user" else "0x Alpha"
            self.chat_display.append(f"<b>[{role}]</b>:\n{msg['content']}\n")

    # ------------------------------------------------------------------
    # Chat sync between devices (export / import)
    # ------------------------------------------------------------------

    def export_chats(self):
        """Export all sessions and messages to a portable JSON backup."""
        default_name = f"0x-alpha-chats-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Chats", default_name, "JSON (*.json)"
        )
        if not file_path:
            return

        data = self.storage.export_all()
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not write file:\n{e}")
            return

        session_count = len(data.get("sessions", []))
        message_count = sum(len(s.get("messages", [])) for s in data.get("sessions", []))
        QMessageBox.information(
            self, "Export Complete",
            f"Exported {session_count} chats ({message_count} messages) to:\n{file_path}\n\n"
            "Copy this file to your other device and use Import there."
        )

    def import_chats(self):
        """Merge sessions/messages from an exported JSON backup (idempotent)."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Chats", "", "JSON (*.json)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", f"Could not read file:\n{e}")
            return

        try:
            added_sessions, added_messages = self.storage.import_data(data)
        except ValueError:
            QMessageBox.warning(self, "Invalid File", "This does not look like a 0x Alpha chat export.")
            return
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", f"Something went wrong while merging:\n{e}")
            return

        self.load_sessions()
        QMessageBox.information(
            self, "Import Complete",
            f"Imported {added_sessions} new chats and {added_messages} messages.\n"
            "Existing chats were kept as-is (imports never duplicate)."
        )

    def send_message(self):
        api_key = self.config.get("api_key")
        if not api_key:
            QMessageBox.warning(self, "API Key Missing", "Please enter an OpenRouter API key to continue.")
            return

        text = self.input_text.toPlainText().strip()
        if not text and not self.attached_images:
            return

        # Prepare messages array
        history = self.storage.get_messages(self.current_session_id)
        api_messages = []

        # System message setting target stealth model context
        api_messages.append({
            "role": "system",
            "content": "You are 0x Alpha, an expert software engineering model optimized for long-horizon multi-step coding tasks."
        })

        # Inject whole workspace context into prompt if checkbox checked
        if self.chk_include_context.isChecked() and self.workspace.root_dir:
            workspace_context = self.workspace.build_context_prompt()
            if workspace_context:
                api_messages.append({
                    "role": "user",
                    "content": f"Workspace Context:\n{workspace_context}"
                })

        # Append existing history
        for msg in history:
            api_messages.append({"role": msg["role"], "content": msg["content"]})

        client = OpenRouterClient(
            api_key=api_key,
            base_url=self.config.get("api_base"),
            model=self.config.get("model", STEALTH_MODEL_ID)
        )

        # Format user's current message with multimodal support
        user_msg_payload = client.format_multimodal_message("user", text, self.attached_images)
        api_messages.append(user_msg_payload)

        # Save user message to database
        self.storage.add_message(self.current_session_id, "user", text, self.attached_images)
        self.chat_display.append(f"<b>[User]</b>:\n{text}\n")

        # Clear inputs
        self.input_text.clear()
        self.attached_images = []
        self.lbl_attachments.setText("")

        # Prepare UI for Streaming Response
        self.chat_display.append("<b>[0x Alpha]</b>:\n")
        self.btn_send.setEnabled(False)

        # Run completion streaming on separate worker thread
        self.worker = CompletionWorker(client, api_messages)
        self.worker.chunk_received.connect(self._handle_chunk)
        self.worker.error_signal.connect(self._handle_error)
        self.worker.finished_signal.connect(self._handle_finished)
        self.worker.start()

    @Slot(str)
    def _handle_chunk(self, chunk: str):
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(chunk)
        self.chat_display.setTextCursor(cursor)

    @Slot(str)
    def _handle_error(self, error_msg: str):
        QMessageBox.critical(self, "Model Error", f"Failed to get response: {error_msg}")
        self.btn_send.setEnabled(True)

    @Slot()
    def _handle_finished(self):
        self.btn_send.setEnabled(True)
        # Extract last assistant message text and persist to storage
        full_text = self.chat_display.toPlainText().split("[0x Alpha]:\n")[-1]
        self.storage.add_message(self.current_session_id, "assistant", full_text)
