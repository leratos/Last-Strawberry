# class_folder/ui/correction_dialog.py
# -*- coding: utf-8 -*-

"""
Ein erweiterter Dialog, der es dem Dungeon Master erlaubt, sowohl den
Erzähltext der KI als auch die extrahierten JSON-Befehle zu korrigieren.
"""

import json
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox, QLabel,
    QMessageBox, QSplitter, QWidget
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt
from typing import Tuple, Optional, List, Dict, Any

class CorrectionDialog(QDialog):
    """Ein Dialog zur Korrektur von KI-generiertem Text und JSON."""

    def __init__(self, original_text: str, original_commands: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("DM-Korrekturwerkzeug")
        self.setMinimumSize(800, 600)

        # --- Widgets ---
        self.narrative_edit = QTextEdit(original_text)
        self.narrative_edit.setAcceptRichText(False)

        # Konvertiere die Befehlsliste in einen formatierten JSON-String für die Anzeige
        try:
            commands_str = json.dumps(original_commands, indent=2, ensure_ascii=False)
        except TypeError:
            commands_str = "[] # Fehler beim Konvertieren der Befehle in JSON"
        
        self.json_edit = QTextEdit(commands_str)
        # Verwende eine Monospace-Schriftart für bessere Lesbarkeit von Code
        monospace_font = QFont("Consolas", 10)
        self.json_edit.setFont(monospace_font)
        self.json_edit.setAcceptRichText(False)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)

        # --- Layout ---
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        narrative_widget = QWidget()
        narrative_layout = QVBoxLayout(narrative_widget)
        narrative_layout.addWidget(QLabel("Erzähltext der KI:"))
        narrative_layout.addWidget(self.narrative_edit)
        
        json_widget = QWidget()
        json_layout = QVBoxLayout(json_widget)
        json_layout.addWidget(QLabel("Extrahierte JSON-Befehle:"))
        json_layout.addWidget(self.json_edit)
        
        splitter.addWidget(narrative_widget)
        splitter.addWidget(json_widget)
        splitter.setSizes([400, 200])

        layout.addWidget(splitter)
        layout.addWidget(button_box)
        
        # --- Verbindungen ---
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)

    def validate_and_accept(self):
        """Prüft vor dem Schließen, ob das eingegebene JSON gültig ist."""
        try:
            # Versuche, das JSON zu parsen, um die Gültigkeit zu prüfen
            json.loads(self.json_edit.toPlainText())
            self.accept()  # Wenn erfolgreich, schließe den Dialog mit "OK"
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Ungültiges JSON",
                                f"Die eingegebenen Befehle sind kein gültiges JSON.\n\nFehler: {e}")

    def get_corrected_data(self) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
        """Gibt die korrigierten Daten zurück, wenn der Dialog akzeptiert wurde."""
        try:
            corrected_text = self.narrative_edit.toPlainText().strip()
            corrected_commands = json.loads(self.json_edit.toPlainText())
            return corrected_text, corrected_commands
        except (json.JSONDecodeError, TypeError):
            return None

