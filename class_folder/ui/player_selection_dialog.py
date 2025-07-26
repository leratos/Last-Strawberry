# class_folder/ui/player_selection_dialog.py
# -*- coding: utf-8 -*-

"""
Dialog zur Auswahl eines lokalen Spielers ohne Passwort-Abfrage.
Zeigt alle in der lokalen DB vorhandenen Benutzer an.
"""

import logging
from typing import Optional, Dict, Any
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QMessageBox, QGroupBox,
    QTextEdit
)
from PySide6.QtCore import Qt

from class_folder.core.database_manager import DatabaseManager

logger = logging.getLogger(__name__)

class PlayerSelectionDialog(QDialog):
    """Dialog zur lokalen Spielerauswahl ohne Passwort."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spieler auswählen - Offline Modus")
        self.setModal(True)
        self.setFixedSize(500, 400)
        
        self.selected_user = None
        self.db_manager = DatabaseManager()
        
        self.setup_ui()
        self.load_users()
        self.apply_style()
    
    def setup_ui(self):
        """Erstellt die Benutzeroberfläche."""
        layout = QVBoxLayout(self)
        
        # Titel und Erklärung
        title_label = QLabel("Lokaler Spieler")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)
        
        info_label = QLabel(
            "Wähle einen Spieler aus der lokalen Datenbank.\n"
            "Für Online-Synchronisation nutze später die Webversion."
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("color: #888; margin-bottom: 20px;")
        layout.addWidget(info_label)
        
        # Spieler-Liste
        users_group = QGroupBox("Verfügbare Spieler")
        users_layout = QVBoxLayout(users_group)
        
        self.users_list = QListWidget()
        self.users_list.itemDoubleClicked.connect(self.on_user_selected)
        users_layout.addWidget(self.users_list)
        
        layout.addWidget(users_group)
        
        # Info-Bereich für ausgewählten Spieler
        info_group = QGroupBox("Spieler-Info")
        info_layout = QVBoxLayout(info_group)
        
        self.user_info = QTextEdit()
        self.user_info.setMaximumHeight(80)
        self.user_info.setReadOnly(True)
        self.user_info.setPlaceholderText("Wähle einen Spieler aus der Liste...")
        info_layout.addWidget(self.user_info)
        
        layout.addWidget(info_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.new_user_button = QPushButton("Neuen Spieler erstellen")
        self.new_user_button.clicked.connect(self.on_create_new_user)
        button_layout.addWidget(self.new_user_button)
        
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        self.select_button = QPushButton("Spieler wählen")
        self.select_button.setDefault(True)
        self.select_button.clicked.connect(self.on_user_selected)
        self.select_button.setEnabled(False)
        button_layout.addWidget(self.select_button)
        
        layout.addLayout(button_layout)
        
        # Liste-Selection ändern
        self.users_list.currentItemChanged.connect(self.on_selection_changed)
    
    def load_users(self):
        """Lädt alle Benutzer aus der lokalen Datenbank."""
        try:
            self.db_manager.setup_database()  # Stelle sicher, dass DB existiert
            users = self.db_manager.get_all_users()
            
            if not users:
                # Erstelle einen Standard-Benutzer wenn keiner existiert
                self.create_default_user()
                users = self.db_manager.get_all_users()
            
            for user in users:
                if user.get('is_active', True):  # Nur aktive Benutzer
                    item = QListWidgetItem()
                    item.setText(f"🎮 {user['username']}")
                    item.setData(Qt.ItemDataRole.UserRole, user)
                    self.users_list.addItem(item)
                    
            logger.info(f"Geladene {len(users)} Benutzer aus lokaler DB")
                    
        except Exception as e:
            logger.error(f"Fehler beim Laden der Benutzer: {e}", exc_info=True)
            QMessageBox.critical(self, "Fehler", 
                               f"Fehler beim Laden der Spieler:\n{e}")
    
    def create_default_user(self):
        """Erstellt einen Standard-Benutzer für lokales Spielen."""
        try:
            user_id = self.db_manager.create_user(
                username="Lokaler_Spieler",
                hashed_password="dummy_hash",  # Wird lokal nicht geprüft
                roles=["player"]
            )
            if user_id:
                logger.info("Standard-Benutzer 'Lokaler_Spieler' erstellt")
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Standard-Benutzers: {e}")
    
    def on_selection_changed(self, current, previous):
        """Wird aufgerufen wenn sich die Auswahl ändert."""
        if current:
            user_data = current.data(Qt.ItemDataRole.UserRole)
            if user_data:
                roles_text = ", ".join(user_data.get('roles', []))
                status = "Aktiv" if user_data.get('is_active', True) else "Inaktiv"
                
                info_text = f"Benutzername: {user_data['username']}\n"
                info_text += f"Rollen: {roles_text}\n"
                info_text += f"Status: {status}"
                
                self.user_info.setText(info_text)
                self.select_button.setEnabled(True)
        else:
            self.user_info.clear()
            self.select_button.setEnabled(False)
    
    def on_user_selected(self):
        """Wird aufgerufen wenn ein Benutzer ausgewählt wird."""
        current_item = self.users_list.currentItem()
        if current_item:
            self.selected_user = current_item.data(Qt.ItemDataRole.UserRole)
            logger.info(f"Spieler ausgewählt: {self.selected_user['username']}")
            self.accept()
    
    def on_create_new_user(self):
        """Öffnet Dialog zur Erstellung eines neuen Benutzers."""
        from PySide6.QtWidgets import QInputDialog
        
        username, ok = QInputDialog.getText(
            self, 
            "Neuen Spieler erstellen", 
            "Benutzername:",
            text="Spieler_1"
        )
        
        if ok and username.strip():
            try:
                user_id = self.db_manager.create_user(
                    username=username.strip(),
                    hashed_password="dummy_hash",  # Wird lokal nicht geprüft
                    roles=["player"]
                )
                
                if user_id:
                    QMessageBox.information(self, "Erfolg", 
                                          f"Spieler '{username}' wurde erstellt!")
                    # Liste neu laden
                    self.users_list.clear()
                    self.load_users()
                else:
                    QMessageBox.warning(self, "Fehler", 
                                      "Benutzername existiert bereits!")
                    
            except Exception as e:
                logger.error(f"Fehler beim Erstellen des Benutzers: {e}")
                QMessageBox.critical(self, "Fehler", 
                                   f"Fehler beim Erstellen:\n{e}")
    
    def get_selected_user(self) -> Optional[Dict[str, Any]]:
        """Gibt den ausgewählten Benutzer zurück."""
        return self.selected_user
    
    def apply_style(self):
        """Wendet das Dark-Theme an."""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Segoe UI', sans-serif;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #3c3c3c;
                border-radius: 6px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #569cd6;
            }
            QListWidget {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
                margin: 2px;
            }
            QListWidget::item:selected {
                background-color: #007acc;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #2d2d30;
            }
            QTextEdit {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 8px;
                color: #d4d4d4;
            }
            QPushButton {
                background-color: #0e639c;
                border: none;
                padding: 10px 16px;
                border-radius: 6px;
                font-weight: bold;
                color: white;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666;
            }
            QLabel {
                color: #d4d4d4;
            }
        """)

    @staticmethod
    def get_player(parent=None) -> Optional[Dict[str, Any]]:
        """Statische Methode zum einfachen Aufruf des Dialogs."""
        dialog = PlayerSelectionDialog(parent)
        if dialog.exec():
            return dialog.get_selected_user()
        return None
