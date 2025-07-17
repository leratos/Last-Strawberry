# class_folder/ui/login_dialog.py
# -*- coding: utf-8 -*-

"""
Ein einfacher Dialog zur Eingabe von Benutzername und Passwort für den Online-Modus.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QDialogButtonBox, QLabel
)
from typing import Tuple

class LoginDialog(QDialog):
    """Ein Dialog zur Eingabe von Anmeldeinformationen."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Online-Anmeldung")
        self.setMinimumWidth(350)

        # Widgets
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("z.B. lara")
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Ihr Passwort")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

        # Layout
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.addRow(QLabel("Benutzername:"), self.username_input)
        form_layout.addRow(QLabel("Passwort:"), self.password_input)
        layout.addLayout(form_layout)
        layout.addWidget(button_box)
        
        # Verbindungen
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def get_credentials(self) -> Tuple[str, str]:
        """Gibt die eingegebenen Daten zurück."""
        return self.username_input.text().strip(), self.password_input.text().strip()
