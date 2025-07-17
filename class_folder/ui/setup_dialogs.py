# class/ui/setup_dialogs.py
# -*- coding: utf-8 -*-

"""
Contains the QDialog classes used for the initial game setup,
including world and character creation, and loading existing games.
V3: WorldCreationDialog now uses dynamic templates from the database.
"""

import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit,
    QDialogButtonBox, QLabel, QComboBox, QMessageBox,
    QListWidget, QListWidgetItem, QPushButton, QHBoxLayout
)
from PySide6.QtCore import Qt
from typing import Dict, Any, List, Optional

from templates.regeln import CREATIVE_PROMPTS

logger = logging.getLogger(__name__)

class LoadGameDialog(QDialog):
    """A dialog to load an existing game or start a new one."""

    def __init__(self, saved_games: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spielstand laden")
        self.setMinimumWidth(400)
        
        self.saved_games = saved_games
        self.selected_game: Optional[Dict[str, Any]] = None

        # --- Widgets ---
        self.game_list_widget = QListWidget()
        for game in self.saved_games:
            item_text = f"Welt: {game['world_name']} (Charakter: {game['player_name']})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, game)
            self.game_list_widget.addItem(item)

        self.load_button = QPushButton("Laden")
        self.new_game_button = QPushButton("Neues Spiel starten")
        self.cancel_button = QPushButton("Abbrechen")

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Wähle einen Spielstand zum Laden:"))
        layout.addWidget(self.game_list_widget)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.new_game_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        # --- Connections ---
        self.load_button.clicked.connect(self.on_load_clicked)
        self.new_game_button.clicked.connect(self.on_new_game_clicked)
        self.cancel_button.clicked.connect(self.reject)
        self.game_list_widget.itemDoubleClicked.connect(self.on_load_clicked)

        # --- Initial State ---
        self.load_button.setEnabled(False)
        if self.game_list_widget.count() > 0:
            self.game_list_widget.setCurrentRow(0)
            self.load_button.setEnabled(True)
        
        self.game_list_widget.currentItemChanged.connect(
            lambda current, prev: self.load_button.setEnabled(current is not None)
        )

    def on_load_clicked(self):
        """Sets the selected game and accepts the dialog."""
        current_item = self.game_list_widget.currentItem()
        if current_item:
            self.selected_game = current_item.data(Qt.UserRole)
            self.accept()

    def on_new_game_clicked(self):
        """Sets the result to indicate a new game should be started."""
        self.selected_game = None
        self.accept()

    def get_selection(self) -> Optional[Dict[str, Any]]:
        """Returns the selected game data, or None to start a new game."""
        return self.selected_game

class WorldCreationDialog(QDialog):
    """A dialog to guide the player through creating a new world using templates."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Erschaffe deine Welt")
        self.setMinimumWidth(500)

        # --- Widgets ---
        self.world_name_input = QLineEdit()
        self.lore_text_edit = QTextEdit()
        self.template_combo = QComboBox()
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

        # --- Layout ---
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.addRow("Name deiner Welt:", self.world_name_input)
        form_layout.addRow("Genre / Thema:", self.template_combo)
        layout.addLayout(form_layout)
        
        layout.addWidget(QLabel("Beschreibe deine Welt (dies ist der erste Prompt für die KI):"))
        self.lore_text_edit.setPlaceholderText("Beschreibe die einzigartigen physikalischen Gesetze, Völker und die Geografie deiner Welt...")
        layout.addWidget(self.lore_text_edit)
        layout.addWidget(self.button_box)
        
        # --- Connections ---
        self.populate_templates()
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def populate_templates(self):
        """Populates the combo box with available genre templates."""
        for key in CREATIVE_PROMPTS.keys():
            # Format the key for display (e.g., "system_survival_horror" -> "Survival Horror")
            display_name = key.replace("system_", "").replace("_", " ").title()
            self.template_combo.addItem(display_name, key)

    def get_data(self) -> Optional[Dict[str, Any]]:
        world_name = self.world_name_input.text().strip()
        lore = self.lore_text_edit.toPlainText().strip()
        if not world_name or not lore:
            QMessageBox.warning(self, "Eingabe fehlt", "Bitte gib sowohl einen Namen für die Welt als auch eine Beschreibung ein.")
            return None
        
        template_key = self.template_combo.currentData()
        
        return {
            "name": world_name,
            "lore": lore,
            "template_key": template_key
        }


class CharacterCreationDialog(QDialog):
    """A dialog for creating the player character."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Erschaffe deinen Charakter")
        self.setMinimumWidth(500)

        # --- Widgets ---
        self.char_name_input = QLineEdit()
        self.backstory_edit = QTextEdit()
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

        # --- Layout ---
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.addRow("Name deines Charakters:", self.char_name_input)
        layout.addLayout(form_layout)
        
        layout.addWidget(QLabel("Schreibe die Hintergrundgeschichte deines Charakters:"))
        self.backstory_edit.setPlaceholderText("Wer bist du? Was treibt dich an? Was ist kürzlich passiert?")
        layout.addWidget(self.backstory_edit)
        layout.addWidget(self.button_box)

        # --- Connections ---
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def get_data(self) -> Optional[Dict[str, Any]]:
        name = self.char_name_input.text().strip()
        backstory = self.backstory_edit.toPlainText().strip()
        if not name or not backstory:
            QMessageBox.warning(self, "Eingabe fehlt", "Bitte gib sowohl einen Namen als auch eine Hintergrundgeschichte ein.")
            return None
        return {
            "name": name,
            "backstory": backstory
        }
