# class_folder/ui/mode_selection_dialog.py
# -*- coding: utf-8 -*-

"""
Ein einfacher Dialog, um den Spielmodus (Online/Offline) auszuwählen.
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt

class ModeSelectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spielmodus auswählen")
        self.setModal(True)
        self.mode = "online"  # Standardwert auf online gesetzt

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Webserver-Modus wird verwendet."))
        layout.addWidget(QLabel("(Lokale Varianten sind temporär deaktiviert)"))

        online_button = QPushButton("Mit Server verbinden")
        online_button.clicked.connect(self.select_online)
        layout.addWidget(online_button)

        # Deaktivierte Buttons für später
        offline_button = QPushButton("Offline (Lokale KI) - Deaktiviert")
        offline_button.setEnabled(False)
        offline_button.setStyleSheet("color: #666; background-color: #333;")
        layout.addWidget(offline_button)

        self.setFixedSize(350, 150)

    def select_offline(self):
        # Momentan deaktiviert
        pass

    def select_online(self):
        self.mode = "online"
        self.accept()

    @staticmethod
    def get_mode(parent=None) -> str:
        """Zeigt den Dialog an und gibt den ausgewählten Modus zurück."""
        dialog = ModeSelectionDialog(parent)
        dialog.exec()
        return dialog.mode
