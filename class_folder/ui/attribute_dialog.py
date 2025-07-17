# class_folder/ui/attribute_dialog.py
# -*- coding: utf-8 -*-

"""
Ein Dialog, der es dem Spieler ermöglicht, Attributspunkte
für seinen Charakter nach einem "Point Buy"-System zu vergeben.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, QSpinBox,
    QDialogButtonBox, QWidget, QHBoxLayout, QSlider
)
from PySide6.QtCore import Qt
from typing import Dict, Optional

class AttributeAllocationDialog(QDialog):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Charakter-Attribute verteilen")
        self.setMinimumWidth(500)

        # --- Konfiguration ---
        self.POINT_BUDGET = 75
        self.ATTRIBUTES = [
            "Stärke", "Geschicklichkeit", "Konstitution",
            "Intelligenz", "Weisheit", "Charisma", "Wahrnehmung"
        ]
        self.MIN_SCORE = 8
        self.MAX_SCORE = 15
        
        # --- Widgets ---
        self.spin_boxes: Dict[str, QSpinBox] = {}
        self.sliders: Dict[str, QSlider] = {}
        
        self.points_label = QLabel()
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

        # --- Layout ---
        main_layout = QVBoxLayout(self)
        
        header_label = QLabel(f"Verteile {self.POINT_BUDGET} Punkte auf deine Attribute.")
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header_label)

        grid_layout = QGridLayout()
        grid_layout.setColumnStretch(1, 1) # Slider-Spalte soll sich ausdehnen
        
        for i, attr_name in enumerate(self.ATTRIBUTES):
            label = QLabel(f"{attr_name}:")
            
            spin_box = QSpinBox()
            spin_box.setRange(self.MIN_SCORE, self.MAX_SCORE)
            spin_box.setValue(10) # Startwert
            self.spin_boxes[attr_name] = spin_box
            
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(self.MIN_SCORE, self.MAX_SCORE)
            slider.setValue(10)
            self.sliders[attr_name] = slider

            # Verbindungen
            spin_box.valueChanged.connect(self.update_points)
            slider.valueChanged.connect(spin_box.setValue)
            spin_box.valueChanged.connect(slider.setValue)

            grid_layout.addWidget(label, i, 0)
            grid_layout.addWidget(slider, i, 1)
            grid_layout.addWidget(spin_box, i, 2)

        main_layout.addLayout(grid_layout)

        self.points_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.points_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        main_layout.addWidget(self.points_label)
        
        main_layout.addWidget(self.button_box)

        # --- Verbindungen ---
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        
        # --- Initialer Zustand ---
        self.update_points()

    def update_points(self):
        """Berechnet die verbleibenden Punkte neu und aktualisiert die Anzeige."""
        total_spent = sum(sb.value() for sb in self.spin_boxes.values())
        remaining = self.POINT_BUDGET - total_spent
        
        self.points_label.setText(f"Verbleibende Punkte: {remaining}")

        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            if remaining == 0:
                ok_button.setEnabled(True)
                self.points_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #4CAF50;") # Grün
            else:
                ok_button.setEnabled(False)
                self.points_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #F44336;") # Rot

    def get_attributes(self) -> Optional[Dict[str, int]]:
        """Gibt das Dictionary der finalen Attribute zurück."""
        total_spent = sum(sb.value() for sb in self.spin_boxes.values())
        if total_spent != self.POINT_BUDGET:
            return None # Sollte durch deaktivierten OK-Button nicht passieren
        
        return {name: sb.value() for name, sb in self.spin_boxes.items()}

