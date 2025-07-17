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
        self.mode = "offline"  # Standardwert

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Wie möchten Sie spielen?"))

        offline_button = QPushButton("Offline (Lokale KI)")
        offline_button.clicked.connect(self.select_offline)
        layout.addWidget(offline_button)

        online_button = QPushButton("Online (Mit Server verbinden)")
        online_button.clicked.connect(self.select_online)
        layout.addWidget(online_button)

        self.setFixedSize(300, 120)

    def select_offline(self):
        self.mode = "offline"
        self.accept()

    def select_online(self):
        self.mode = "online"
        self.accept()

    @staticmethod
    def get_mode(parent=None) -> str:
        """Zeigt den Dialog an und gibt den ausgewählten Modus zurück."""
        dialog = ModeSelectionDialog(parent)
        dialog.exec()
        return dialog.mode
