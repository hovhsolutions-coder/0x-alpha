import uuid
import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
    QTextEdit, QPushButton, QFileDialog, QLabel, QLineEdit,
    QSplitter, QCheckBox, QMessageBox, QListWidgetItem
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont

from config import ConfigManager, STEALTH_MODEL_ID
from storage import StorageManager
from sync import GistSync
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
        self.syncer = GistSync(
            get_setting=self.config.get,
            export_all=self.storage.export_all,
            import_all=self.storage.import_all,
        )

        self.current_session_id = None
        self.attached_images = []
        self.active_worker = None

        self._init_ui()
        self._apply_dark_theme()
        self.load_sessions()

        # Cross-device chat sync: pull remote chats at startup, then push
        # local state so both devices converge on the same chat history.
        if self.syncer.is_configured:
            self._sync_now(initial=True)

    # ------------------------------------------------------------------
    # Sync helpers
    # ------------------------------------------------------------------

    def _sync_now(self, initial: bool = False):
        """Pull remote chats into the local DB and push the merged result.

        Because import_all merges (nothing is deleted), pulling and pushing
        in sequence converges both devices without data loss.
        """
        try:
            pulled = self.syncer.pull()
            pushed = self.syncer.push()
            if initial and (pulled or pushed):
                self.load_sessions()   # refresh sidebar after merge
                if pulled:
                    print("Chat sync: remote chats merged.")
            elif not (pulled or pushed):
                print("Chat sync: skipped (offline or not configured).")
        except Exception as e:
            print(f"Chat sync failed: {e}")

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

        # --- Chat Sync section ---
        sidebar_layout.addWidget(QLabel("<b>Cross-device Sync</b>"))

        self.chk_sync_enabled = QCheckBox("Sync chats via GitHub Gist")
        self.chk_sync_enabled.setChecked(bool(self.config.get("sync_enabled", False)))
        self.chk_sync_enabled.toggled.connect(self._on_sync_toggled)
        sidebar_layout.addWidget(self.chk_sync_enabled)

        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("GitHub token (gist scope)...")
        self.token_input.setEchoMode(QLineEdit.Password)
        self.token_input.setText(self.config.get("sync_github_token", ""))
        self.token_input.textChanged.connect(self._on_sync_settings_changed)
        sidebar_layout.addWidget(self.token_input)

        gist_row = QHBoxLayout()
        self.gist_input = QLineEdit()
        self.gist_input.setPlaceholderText("Gist ID...")
        self.gist_input.setText(self.config.get("sync_gist_id", ""))
        self.gist_input.textChanged.connect(self._on_sync_settings_changed)
        gist_row.addWidget(self.gist_input)

        self.btn_create_gist = QPushButton("+")
        self.btn_create_gist.setToolTip("Create a new private sync gist")
        self.btn_create_gist.setFixedWidth(32)
        self.btn_create_gist.clicked.connect(self._create_sync_gist)
        gist_row.addWidget(self.btn_create_gist)
        sidebar_layout.addLayout(gist_row)

        self.btn_sync_now = QPushButton("⟳ Sync now")
        self.btn_sync_now.clicked.connect(lambda: self._sync_now())
        sidebar_layout.addWidget(self.btn_sync_now)

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

    # ------------------------------------------------------------------
    # Sync UI handlers
    # ------------------------------------------------------------------

    def _on_sync_toggled(self, checked: bool):
        self.config.set("sync_enabled", bool(checked))

    def _on_sync_settings_changed(self, text: str):
        self.config.set("sync_github_token", self.token_input.text().strip())
        self.config.set("sync_gist_id", self.gist_input.text().strip())

    def _create_sync_gist(self):
        if not self.token_input.text().strip():
            QMessageBox.warning(self, "Token Missing",
                                "Enter a GitHub token with gist scope first.")
            return
        gist_id = self.syncer.create_sync_gist()
        if gist_id:
            self.gist_input.setText(gist_id)
            QMessageBox.information(self, "Sync Gist Created",
                                    f"Private sync gist created.\n\nID: {gist_id}")
        else:
            QMessageBox.critical(self, "Failed",
                                 "Could not create the sync gist. Check your token.")

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

        # Push the updated conversation to the sync backend (best-effort)
        if self.config.get("sync_enabled", False) and self.syncer.is_configured:
            self._sync_now()
