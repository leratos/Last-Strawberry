# class_folder/ui/settings_dialog.py
# -*- coding: utf-8 -*-

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QDialogButtonBox, QLabel
)
from typing import Tuple

class SettingsDialog(QDialog):
    """Ein Dialog zur Eingabe von Server-URL und API-Key."""
    def __init__(self, current_url: str = "", current_api_key: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Server-Einstellungen")
        self.setMinimumWidth(450)

        # Widgets
        self.url_input = QLineEdit(current_url)
        self.url_input.setPlaceholderText("z.B. http://127.0.0.1:8000")
        
        self.api_key_input = QLineEdit(current_api_key)
        self.api_key_input.setPlaceholderText("Ihr persönlicher API-Schlüssel")
        # Verbirgt die Eingabe des API-Keys
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)

        # Layout
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.addRow(QLabel("Server-Adresse (URL):"), self.url_input)
        form_layout.addRow(QLabel("API-Schlüssel:"), self.api_key_input)
        layout.addLayout(form_layout)
        layout.addWidget(button_box)
        
        # Verbindungen
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def get_data(self) -> Tuple[str, str]:
        """Gibt die eingegebenen Daten zurück."""
        return self.url_input.text().strip(), self.api_key_input.text().strip()