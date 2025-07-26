# class_folder/ui/settings_dialog.py
# -*- coding: utf-8 -*-

"""
Einstellungsdialog für Cloud-KI-Service Konfiguration.
Ermöglicht die Konfiguration von Cloud-KI-Services wie Google Cloud Run.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QLineEdit, QTextEdit, QGroupBox, QRadioButton, QButtonGroup,
    QFileDialog, QMessageBox, QTabWidget, QWidget, QFormLayout,
    QCheckBox, QDialogButtonBox
)
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Dialog für die Anwendungseinstellungen."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen - Last-Strawberry")
        self.setModal(True)
        self.setFixedSize(600, 500)
        
        self.settings = self.load_settings()
        
        self.setup_ui()
        self.load_current_settings()
        self.apply_style()
    
    def setup_ui(self):
        """Erstellt die Benutzeroberfläche."""
        layout = QVBoxLayout(self)
        
        # Tab-Widget für verschiedene Einstellungsgruppen
        self.tab_widget = QTabWidget()
        
        # KI-Service Tab
        ki_tab = self.create_ki_service_tab()
        self.tab_widget.addTab(ki_tab, "🤖 KI-Service")
        
        # Allgemeine Einstellungen Tab
        general_tab = self.create_general_tab()
        self.tab_widget.addTab(general_tab, "⚙️ Allgemein")
        
        layout.addWidget(self.tab_widget)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.test_button = QPushButton("🧪 Verbindung testen")
        self.test_button.clicked.connect(self.test_connection)
        button_layout.addWidget(self.test_button)
        
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        self.save_button = QPushButton("Speichern")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_button)
        
        layout.addLayout(button_layout)
        
        # Initial state nach Erstellung aller UI-Elemente
        self.on_service_changed()
    
    def create_ki_service_tab(self) -> QWidget:
        """Erstellt den KI-Service Einstellungs-Tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # KI-Service Auswahl
        service_group = QGroupBox("KI-Service Auswahl")
        service_layout = QVBoxLayout(service_group)
        
        self.service_group = QButtonGroup()
        
        self.local_radio = QRadioButton("🖥️ Lokale KI (Offline)")
        self.local_radio.setChecked(True)
        self.service_group.addButton(self.local_radio, 0)
        service_layout.addWidget(self.local_radio)
        
        self.cloud_radio = QRadioButton("☁️ Cloud KI-Service")
        self.service_group.addButton(self.cloud_radio, 1)
        service_layout.addWidget(self.cloud_radio)
        
        layout.addWidget(service_group)
        
        # Cloud-Service Konfiguration
        self.cloud_group = QGroupBox("Cloud-Service Konfiguration")
        cloud_layout = QFormLayout(self.cloud_group)
        
        # Service URL
        self.service_url_edit = QLineEdit()
        self.service_url_edit.setPlaceholderText("z.B. http://127.0.0.1:8080 (lokal) oder https://your-service.run.app (cloud)")
        self.service_url_edit.textChanged.connect(self.on_url_changed)
        cloud_layout.addRow("🌐 Service URL:", self.service_url_edit)
        
        # API Key File (optional für lokale URLs)
        self.api_key_section = QWidget()
        api_key_section_layout = QFormLayout(self.api_key_section)
        api_key_section_layout.setContentsMargins(0, 0, 0, 0)
        
        api_key_layout = QHBoxLayout()
        self.api_key_path_edit = QLineEdit()
        self.api_key_path_edit.setPlaceholderText("Pfad zur API-Key JSON-Datei (optional für lokale APIs)")
        self.api_key_path_edit.setReadOnly(True)
        
        self.browse_key_button = QPushButton("📁 Durchsuchen")
        self.browse_key_button.clicked.connect(self.browse_api_key_file)
        
        api_key_layout.addWidget(self.api_key_path_edit)
        api_key_layout.addWidget(self.browse_key_button)
        api_key_section_layout.addRow("🔐 API-Key Datei:", api_key_layout)
        
        # API Key Preview
        self.api_key_preview = QTextEdit()
        self.api_key_preview.setMaximumHeight(100)
        self.api_key_preview.setReadOnly(True)
        self.api_key_preview.setPlaceholderText("API-Key Inhalt (für Cloud-APIs erforderlich)")
        api_key_section_layout.addRow("📋 Key Preview:", self.api_key_preview)
        
        cloud_layout.addRow(self.api_key_section)
        
        # Connection Timeout
        self.timeout_edit = QLineEdit()
        self.timeout_edit.setText("30")
        self.timeout_edit.setPlaceholderText("30")
        cloud_layout.addRow("⏱️ Timeout (Sek.):", self.timeout_edit)
        
        layout.addWidget(self.cloud_group)
        
        # Event-Verbindungen
        self.cloud_radio.toggled.connect(self.on_service_changed)
        self.local_radio.toggled.connect(self.on_service_changed)
        
        return widget
    
    def create_general_tab(self) -> QWidget:
        """Erstellt den allgemeinen Einstellungs-Tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Logging
        logging_group = QGroupBox("Logging & Debug")
        logging_layout = QFormLayout(logging_group)
        
        self.debug_logging_check = QCheckBox("Erweiterte Debug-Logs aktivieren")
        logging_layout.addRow(self.debug_logging_check)
        
        self.log_to_file_check = QCheckBox("Logs in Datei speichern")
        self.log_to_file_check.setChecked(True)
        logging_layout.addRow(self.log_to_file_check)
        
        layout.addWidget(logging_group)
        
        # UI Einstellungen
        ui_group = QGroupBox("Benutzeroberfläche")
        ui_layout = QFormLayout(ui_group)
        
        self.dark_theme_check = QCheckBox("Dark Theme verwenden")
        self.dark_theme_check.setChecked(True)
        ui_layout.addRow(self.dark_theme_check)
        
        layout.addWidget(ui_group)
        
        layout.addStretch()
        
        return widget
    
    def on_service_changed(self):
        """Wird aufgerufen wenn sich die Service-Auswahl ändert."""
        is_cloud = self.cloud_radio.isChecked()
        self.cloud_group.setEnabled(is_cloud)
        
        # Test-Button nur aktivieren wenn er existiert
        if hasattr(self, 'test_button'):
            self.test_button.setEnabled(is_cloud)
        
        # Bei Aktivierung des Cloud-Modus, prüfe URL für API-Key-Bedarf
        if is_cloud:
            self.on_url_changed()
    
    def on_url_changed(self):
        """Wird aufgerufen wenn sich die URL ändert."""
        url = self.service_url_edit.text().lower()
        is_local = url.startswith('http://127.0.0.1') or url.startswith('http://localhost')
        
        # API-Key-Sektion nur für nicht-lokale URLs anzeigen
        if hasattr(self, 'api_key_section'):
            self.api_key_section.setVisible(not is_local)
        
        if is_local and hasattr(self, 'api_key_preview'):
            self.api_key_path_edit.clear()
            self.api_key_preview.setText("🏠 Lokale API - Keine Authentifizierung erforderlich")
        elif hasattr(self, 'api_key_preview'):
            self.api_key_preview.setPlaceholderText("API-Key Inhalt (für Cloud-APIs erforderlich)")
            if not self.api_key_path_edit.text():
                self.api_key_preview.clear()
    
    def browse_api_key_file(self):
        """Öffnet einen Datei-Dialog zur Auswahl der API-Key-Datei."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "API-Key JSON-Datei auswählen",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            self.api_key_path_edit.setText(file_path)
            self.load_api_key_preview(file_path)
    
    def load_api_key_preview(self, file_path: str):
        """Lädt eine Vorschau des API-Keys."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                key_data = json.load(f)
            
            # Erstelle eine sichere Vorschau (ohne sensitive Daten)
            preview_data = {}
            safe_keys = ['type', 'project_id', 'client_email', 'auth_uri', 'token_uri']
            
            for key in safe_keys:
                if key in key_data:
                    preview_data[key] = key_data[key]
            
            if 'private_key_id' in key_data:
                preview_data['private_key_id'] = f"{key_data['private_key_id'][:8]}..."
            
            preview_text = json.dumps(preview_data, indent=2, ensure_ascii=False)
            self.api_key_preview.setText(preview_text)
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der API-Key Vorschau: {e}")
            self.api_key_preview.setText(f"Fehler beim Laden: {e}")
    
    def test_connection(self):
        """Testet die Verbindung zum Cloud-Service."""
        if not self.cloud_radio.isChecked():
            return
        
        service_url = self.service_url_edit.text().strip()
        
        if not service_url:
            QMessageBox.warning(self, "Fehler", "Bitte geben Sie eine Service-URL an.")
            return
        
        # Prüfe ob es sich um eine lokale URL handelt
        is_local = service_url.lower().startswith('http://127.0.0.1') or service_url.lower().startswith('http://localhost')
        
        if not is_local:
            # Für externe APIs ist ein API-Key erforderlich
            api_key_path = self.api_key_path_edit.text().strip()
            if not api_key_path or not Path(api_key_path).exists():
                QMessageBox.warning(self, "Fehler", "Für externe APIs ist eine gültige API-Key-Datei erforderlich.")
                return
        
        try:
            # Erstelle temporären Cloud-Service für Test
            from ..core.cloud_inference_service import CloudInferenceService
            
            api_key_path = self.api_key_path_edit.text().strip() if not is_local else None
            timeout = int(self.timeout_edit.text() or 30)
            
            test_service = CloudInferenceService(
                service_url=service_url,
                api_key_path=api_key_path,
                timeout=timeout
            )
            
            # Teste Verbindung
            if test_service.test_connection():
                if is_local:
                    test_message = f"✅ Verbindung zu lokaler API {service_url} erfolgreich!\n\n" \
                                 "🏠 Lokale API ist bereit für Anfragen."
                else:
                    test_message = f"✅ Verbindung zu Cloud-API {service_url} erfolgreich!\n\n" \
                                 "☁️ Cloud-Service ist bereit für Anfragen."
            else:
                test_message = f"⚠️ Verbindung zu {service_url} nicht optimal.\n\n" \
                             "Der Service ist möglicherweise erreichbar, aber der Test war nicht eindeutig."
            
            QMessageBox.information(self, "Verbindungstest", test_message)
            
            # Cleanup
            test_service.cleanup()
            
        except Exception as e:
            logger.error(f"Verbindungstest fehlgeschlagen: {e}")
            QMessageBox.critical(
                self, 
                "Verbindungstest fehlgeschlagen", 
                f"❌ Fehler bei der Verbindung:\n{e}"
            )
    
    def load_current_settings(self):
        """Lädt die aktuellen Einstellungen in die UI."""
        # KI-Service Einstellungen
        if self.settings.get('ki_service', {}).get('use_cloud', False):
            self.cloud_radio.setChecked(True)
        else:
            self.local_radio.setChecked(True)
        
        cloud_settings = self.settings.get('ki_service', {}).get('cloud', {})
        self.service_url_edit.setText(cloud_settings.get('service_url', ''))
        self.timeout_edit.setText(str(cloud_settings.get('timeout', 30)))
        
        api_key_path = cloud_settings.get('api_key_path', '')
        if api_key_path:
            self.api_key_path_edit.setText(api_key_path)
            if Path(api_key_path).exists():
                self.load_api_key_preview(api_key_path)
        
        # Allgemeine Einstellungen
        general = self.settings.get('general', {})
        self.debug_logging_check.setChecked(general.get('debug_logging', False))
        self.log_to_file_check.setChecked(general.get('log_to_file', True))
        self.dark_theme_check.setChecked(general.get('dark_theme', True))
        
        self.on_service_changed()
    
    def save_settings(self):
        """Speichert die Einstellungen."""
        try:
            # KI-Service Einstellungen
            self.settings['ki_service'] = {
                'use_cloud': self.cloud_radio.isChecked(),
                'cloud': {
                    'service_url': self.service_url_edit.text().strip(),
                    'api_key_path': self.api_key_path_edit.text().strip(),
                    'timeout': int(self.timeout_edit.text() or 30)
                }
            }
            
            # Allgemeine Einstellungen
            self.settings['general'] = {
                'debug_logging': self.debug_logging_check.isChecked(),
                'log_to_file': self.log_to_file_check.isChecked(),
                'dark_theme': self.dark_theme_check.isChecked()
            }
            
            # Validierung für Cloud-Service
            if self.cloud_radio.isChecked():
                service_url = self.service_url_edit.text().strip()
                
                if not service_url:
                    QMessageBox.warning(self, "Fehler", "Bitte geben Sie eine Service-URL an.")
                    return
                
                # Prüfe ob es sich um eine lokale URL handelt
                is_local = service_url.lower().startswith('http://127.0.0.1') or service_url.lower().startswith('http://localhost')
                
                if not is_local:
                    # Für externe APIs ist ein API-Key erforderlich
                    api_key_path = self.api_key_path_edit.text().strip()
                    if not api_key_path or not Path(api_key_path).exists():
                        QMessageBox.warning(self, "Fehler", "Für externe Cloud-APIs ist eine gültige API-Key-Datei erforderlich.")
                        return
            
            # Speichern
            self.save_settings_to_file()
            
            QMessageBox.information(self, "Gespeichert", "Einstellungen wurden erfolgreich gespeichert!")
            self.accept()
            
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Einstellungen: {e}")
            QMessageBox.critical(self, "Fehler", f"Fehler beim Speichern:\n{e}")
    
    def load_settings(self) -> Dict[str, Any]:
        """Lädt die Einstellungen aus der Datei."""
        settings_file = Path("settings.json")
        default_settings = {
            'ki_service': {
                'use_cloud': False,
                'cloud': {
                    'service_url': 'http://127.0.0.1:8080',  # Standard für lokale Tests
                    'api_key_path': '',
                    'timeout': 30
                }
            },
            'general': {
                'debug_logging': False,
                'log_to_file': True,
                'dark_theme': True
            }
        }
        
        if settings_file.exists():
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                
                # Merge mit default settings
                for key, value in default_settings.items():
                    if key not in loaded_settings:
                        loaded_settings[key] = value
                    elif isinstance(value, dict):
                        for subkey, subvalue in value.items():
                            if subkey not in loaded_settings[key]:
                                loaded_settings[key][subkey] = subvalue
                
                return loaded_settings
                
            except Exception as e:
                logger.error(f"Fehler beim Laden der Einstellungen: {e}")
        
        return default_settings
    
    def save_settings_to_file(self):
        """Speichert die Einstellungen in eine Datei."""
        settings_file = Path("settings.json")
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, indent=2, ensure_ascii=False)
    
    def get_settings(self) -> Dict[str, Any]:
        """Gibt die aktuellen Einstellungen zurück."""
        return self.settings
    
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
            QTabWidget::pane {
                border: 1px solid #3c3c3c;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #2d2d30;
                color: #d4d4d4;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #007acc;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #3c3c3c;
            }
            QLineEdit, QTextEdit {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 8px;
                color: #d4d4d4;
            }
            QLineEdit:focus, QTextEdit:focus {
                border-color: #007acc;
            }
            QPushButton {
                background-color: #0e639c;
                border: none;
                padding: 8px 16px;
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
            QRadioButton, QCheckBox {
                color: #d4d4d4;
                spacing: 8px;
            }
            QRadioButton::indicator, QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QRadioButton::indicator:unchecked {
                border: 2px solid #666;
                border-radius: 8px;
                background-color: transparent;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #007acc;
                border-radius: 8px;
                background-color: #007acc;
            }
            QCheckBox::indicator:unchecked {
                border: 2px solid #666;
                border-radius: 3px;
                background-color: transparent;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #007acc;
                border-radius: 3px;
                background-color: #007acc;
            }
            QLabel {
                color: #d4d4d4;
            }
        """)

    @staticmethod
    def show_settings(parent=None) -> Optional[Dict[str, Any]]:
        """Zeigt den Einstellungsdialog an und gibt die Einstellungen zurück."""
        dialog = SettingsDialog(parent)
        if dialog.exec():
            return dialog.get_settings()
        return None