# class_folder/ui/level_up_dialog.py
# -*- coding: utf-8 -*-

"""
Ein Dialog, der beim Stufenaufstieg angezeigt wird und es dem Spieler
ermöglicht, neue Attributspunkte zu verteilen.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, QPushButton,
    QDialogButtonBox, QWidget
)
from PySide6.QtCore import Qt, Signal
from typing import Dict

class LevelUpDialog(QDialog):
    def __init__(self, current_attributes: Dict[str, int], points_to_spend: int, parent: QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Stufenaufstieg!")
        self.setMinimumWidth(400)

        self.attributes = current_attributes.copy()
        self.points_to_spend = points_to_spend
        self.points_spent = 0

        # --- Widgets ---
        self.attr_labels: Dict[str, QLabel] = {}
        self.points_label = QLabel()
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)

        # --- Layout ---
        main_layout = QVBoxLayout(self)
        
        header_label = QLabel(f"Glückwunsch! Verteile {self.points_to_spend} neue Attributspunkte.")
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        main_layout.addWidget(header_label)

        grid_layout = QGridLayout()
        
        for i, (attr_name, attr_value) in enumerate(self.attributes.items()):
            label = QLabel(f"{attr_name}:")
            value_label = QLabel(str(attr_value))
            value_label.setStyleSheet("font-weight: bold;")
            self.attr_labels[attr_name] = value_label
            
            plus_button = QPushButton("+")
            plus_button.clicked.connect(lambda checked=False, name=attr_name: self.change_attribute(name, 1))
            
            minus_button = QPushButton("-")
            minus_button.clicked.connect(lambda checked=False, name=attr_name: self.change_attribute(name, -1))

            grid_layout.addWidget(label, i, 0)
            grid_layout.addWidget(value_label, i, 1)
            grid_layout.addWidget(minus_button, i, 2)
            grid_layout.addWidget(plus_button, i, 3)

        main_layout.addLayout(grid_layout)

        self.points_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.points_label)
        
        main_layout.addWidget(self.button_box)

        # --- Verbindungen ---
        self.button_box.accepted.connect(self.accept)
        
        # --- Initialer Zustand ---
        self.update_display()

    def change_attribute(self, attr_name: str, delta: int):
        """Erhöht oder verringert einen Attributwert."""
        if delta > 0 and self.points_spent < self.points_to_spend:
            self.attributes[attr_name] += 1
            self.points_spent += 1
        elif delta < 0 and self.attributes[attr_name] > 0 and self.points_spent > 0:
            # Stelle sicher, dass der ursprüngliche Wert nicht unterschritten wird
            # (Diese Logik kann verfeinert werden, wenn nötig)
            self.attributes[attr_name] -= 1
            self.points_spent -= 1
        
        self.update_display()

    def update_display(self):
        """Aktualisiert alle Anzeigen."""
        for name, label in self.attr_labels.items():
            label.setText(str(self.attributes[name]))
            
        points_left = self.points_to_spend - self.points_spent
        self.points_label.setText(f"Verbleibende Punkte: {points_left}")
        
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setEnabled(points_left == 0)

    def get_new_attributes(self) -> Dict[str, int]:
        """Gibt das Dictionary der neuen Attribute zurück."""
        return self.attributes
