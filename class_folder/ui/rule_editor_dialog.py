# class_folder/ui/rule_editor_dialog.py
# -*- coding: utf-8 -*-

"""
A powerful dialog for viewing, editing, adding, deleting, and reordering AI prompt rules.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QAbstractItemView,
    QDialogButtonBox, QMessageBox
)
from PySide6.QtCore import Qt
from typing import List, Dict, Any

class RuleEditorDialog(QDialog):
    """A dialog to visually edit a list of AI rules."""

    def __init__(self, rules: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("KI-Regel-Editor")
        self.setMinimumSize(700, 500)

        # Store the initial rules. We work on a copy.
        self.rules = [dict(r) for r in rules]

        # --- Widgets ---
        self.rule_list_widget = QListWidget()
        self.rule_list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.rule_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.add_button = QPushButton("Neue Regel")
        self.edit_button = QPushButton("Bearbeiten")
        self.delete_button = QPushButton("Löschen")
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)

        # --- Layout ---
        main_layout = QVBoxLayout(self)
        
        list_layout = QHBoxLayout()
        list_layout.addWidget(self.rule_list_widget, 4) # List takes more space

        controls_layout = QVBoxLayout()
        controls_layout.addWidget(self.add_button)
        controls_layout.addWidget(self.edit_button)
        controls_layout.addWidget(self.delete_button)
        controls_layout.addStretch()
        list_layout.addLayout(controls_layout, 1) # Controls take less space
        
        main_layout.addLayout(list_layout)
        main_layout.addWidget(self.button_box)

        # --- Connections ---
        self.add_button.clicked.connect(self.add_rule)
        self.edit_button.clicked.connect(self.edit_rule)
        self.delete_button.clicked.connect(self.delete_rule)
        self.rule_list_widget.itemDoubleClicked.connect(self.edit_rule)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        
        # --- Initial Population ---
        self.populate_list()

    def populate_list(self):
        """Clears and fills the list widget from the self.rules list."""
        self.rule_list_widget.clear()
        for rule in self.rules:
            # We only care about the content for display
            item = QListWidgetItem(rule['content'])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.rule_list_widget.addItem(item)

    def add_rule(self):
        """Adds a new, empty rule to the list for editing."""
        new_item = QListWidgetItem("Neue Regel hier eingeben...")
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.rule_list_widget.addItem(new_item)
        self.rule_list_widget.setCurrentItem(new_item)
        self.rule_list_widget.editItem(new_item)

    def edit_rule(self):
        """Edits the currently selected rule."""
        selected_item = self.rule_list_widget.currentItem()
        if selected_item:
            self.rule_list_widget.editItem(selected_item)

    def delete_rule(self):
        """Deletes the currently selected rule with confirmation."""
        selected_item = self.rule_list_widget.currentItem()
        if not selected_item:
            return
        
        reply = QMessageBox.question(self, "Regel löschen", 
                                     f"Möchten Sie die Regel wirklich löschen?\n\n'{selected_item.text()}'",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            row = self.rule_list_widget.row(selected_item)
            self.rule_list_widget.takeItem(row)

    def get_updated_rules(self) -> List[Dict[str, Any]]:
        """
        Returns the final list of rules, reflecting all changes (edits, reorders).
        """
        final_rules = []
        for i in range(self.rule_list_widget.count()):
            item = self.rule_list_widget.item(i)
            # Reconstruct the rule dictionary
            # We assign a new order_index based on the final position
            rule_dict = {
                'content': item.text(),
                'order_index': (i + 1) * 10, # e.g., 10, 20, 30...
                'is_active': True, # Assume all rules in the editor are active
                'rule_type': 'RULE' # Default type for now
            }
            final_rules.append(rule_dict)
        return final_rules

    def accept(self):
        """Overrides the default accept to ensure rules are updated before closing."""
        # Update self.rules with the final state from the widget
        self.rules = self.get_updated_rules()
        super().accept()
