# game_main.py
# -*- coding: utf-8 -*-

"""
Hauptanwendung für das 'Last-Strawberry' KI Text-Adventure.
Einstiegspunkt, der die UI erstellt und das Spiel startet.
Unterstützt sowohl Offline- als auch Online-Modus.
"""

import sys
import os
import logging
import json
from typing import Optional
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTextBrowser,
    QLineEdit, QHBoxLayout, QPushButton, QSplitter, QLabel, QMessageBox,
    QGroupBox
)

# Korrigierte Importpfade
from class_folder.game_logic.game_manager import GameManager
from class_folder.core.inference_service import InferenceService
from class_folder.core.cloud_inference_service import CloudInferenceService
from class_folder.ui.player_selection_dialog import PlayerSelectionDialog
from class_folder.ui.settings_dialog import SettingsDialog
from class_folder.core.database_manager import DatabaseManager

# Logging-Konfiguration
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Console Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# File Handler
file_handler = logging.FileHandler('app_debug.log', encoding='utf-8')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

logger.info('Logger initialized. Starting application...')


class AdventureWindow(QMainWindow):
    """Das Hauptfenster für das Text-Abenteuer - Nur Offline-Modus."""

    def __init__(self):
        super().__init__()
        logger.info('AdventureWindow wird initialisiert...')
        
        self.setWindowTitle("Last-Strawberry - KI Text-Adventure")

        self.setGeometry(100, 100, 1400, 900)

        self.game_manager: Optional[GameManager] = None
        self.inference_service: Optional[InferenceService] = None
        self.current_user: Optional[dict] = None
        self.db_manager: Optional[DatabaseManager] = None
        self.settings: Optional[dict] = None

        self.setup_ui()
        self.apply_stylesheet()
        self.load_settings()
        
        # Starte die Initialisierung nach dem Event-Loop-Start
        QTimer.singleShot(0, self.start_player_selection)

    def setup_ui(self):
        """Erstellt und arrangiert die UI-Widgets."""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # Hauptsplitter
        splitter = QSplitter(self)
        
        # Linkes Panel - Spielbereich
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Story-Anzeige
        story_group = QGroupBox("Abenteuer")
        story_layout = QVBoxLayout(story_group)
        self.story_display = QTextBrowser()
        self.story_display.setMinimumHeight(400)
        story_layout.addWidget(self.story_display)
        left_layout.addWidget(story_group)
        
        # Eingabebereich
        input_group = QGroupBox("Dein Befehl")
        input_layout = QVBoxLayout(input_group)
        input_control_layout = QHBoxLayout()
        
        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("Was möchtest du tun?")
        self.send_button = QPushButton("Senden")
        self.send_button.setMinimumWidth(100)
        
        input_control_layout.addWidget(self.input_line)
        input_control_layout.addWidget(self.send_button)
        input_layout.addLayout(input_control_layout)
        left_layout.addWidget(input_group)
        
        # Rechtes Panel - Status und Steuerung
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_panel.setMaximumWidth(400)
        right_panel.setMinimumWidth(350)
        
        # Charakter-Status
        status_group = QGroupBox("Charakter-Status")
        status_layout = QVBoxLayout(status_group)
        self.status_display = QTextBrowser()
        self.status_display.setMaximumHeight(200)
        status_layout.addWidget(self.status_display)
        right_layout.addWidget(status_group)
        
        # Spielsteuerung
        control_group = QGroupBox("Spielsteuerung")

        control_group.setObjectName("control_group")  # Für späteren Zugriff

        control_layout = QVBoxLayout(control_group)
        
        self.correct_button = QPushButton("Letzte Antwort korrigieren")
        self.save_button = QPushButton("Spiel speichern")
        self.settings_button = QPushButton("⚙️ Einstellungen")
        
        control_layout.addWidget(self.correct_button)
        control_layout.addWidget(self.save_button)
        control_layout.addWidget(self.settings_button)

        control_layout.addStretch()
        right_layout.addWidget(control_group)
        
        # Hinzufügen der Panels zum Splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([1000, 400])
        main_layout.addWidget(splitter)
        
        # Event-Verbindungen
        self.send_button.clicked.connect(self.on_send_command)
        self.input_line.returnPressed.connect(self.on_send_command)
        self.correct_button.clicked.connect(self.on_correct_last_answer)
        self.save_button.clicked.connect(self.on_save_game)
        self.settings_button.clicked.connect(self.on_open_settings)

    def apply_stylesheet(self):
        """Wendet das moderne Dark-Theme an."""
        self.setStyleSheet("""
            QMainWindow, QWidget { 
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
            QTextBrowser { 
                background-color: #252526; 
                border: 1px solid #3c3c3c; 
                font-family: 'Consolas', monospace; 
                font-size: 14px; 
                padding: 12px;
                border-radius: 4px;
                line-height: 1.4;
            }
            QLineEdit { 
                background-color: #2d2d30; 
                border: 2px solid #404040; 
                padding: 10px; 
                font-size: 14px; 
                border-radius: 6px; 
                color: #d4d4d4;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
            QPushButton { 
                background-color: #0e639c; 
                border: none; 
                padding: 10px 16px; 
                border-radius: 6px; 
                font-weight: bold;
                color: white;
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

    def start_player_selection(self):
        """Startet die Spielerauswahl und bietet direkt Einstellungszugriff."""

        logger.info('Starte Spielerauswahl...')
        
        # Zeige Player-Selection-Dialog
        selected_user = PlayerSelectionDialog.get_player(self)
        if not selected_user:
            logger.info("Keine Spielerauswahl - Anwendung wird beendet")
            self.close()
            return
        
        self.current_user = selected_user
        self.db_manager = DatabaseManager()
        
        logger.info(f"Spieler ausgewählt: {selected_user['username']} (ID: {selected_user['user_id']})")
        
        # Ermögliche Einstellungen sofort nach Spielerauswahl
        self.show_startup_options()

    def show_startup_options(self):
        """Zeigt Optionen vor dem Spielstart an."""
        service_mode = "Cloud-API" if self.is_cloud_mode() else "Lokale KI"
        
        # Update window title
        self.setWindowTitle(f"Last-Strawberry - {self.current_user['username']} ({service_mode})")
        
        # Zeige Info und Einstellungsoptionen
        self.story_display.setHtml(f"""
        <div style='color: #dcdcaa; text-align: center; padding: 30px;'>
            <h2>🎮 Willkommen, {self.current_user['username']}!</h2>
            <h3>Aktueller Modus: <span style='color: #4caf50;'>{service_mode}</span></h3>
            
            <div style='margin: 30px 0; padding: 20px; background-color: #2d2d30; border-radius: 8px;'>
                <p><strong>💡 Hinweis:</strong></p>
                <p>• <strong>Lokale KI:</strong> Verwendet dein lokales NVIDIA GPU-Modell (benötigt CUDA)</p>
                <p>• <strong>Cloud-API:</strong> Nutzt einen externen KI-Service (z.B. 127.0.0.1:8080)</p>
                <br>
                <p>Klicken Sie auf <strong>"⚙️ Einstellungen"</strong> um den Modus zu wechseln,<br>
                oder auf <strong>"🚀 Spiel starten"</strong> um mit dem aktuellen Modus zu beginnen.</p>
            </div>
        </div>
        """)
        
        # Aktiviere Einstellungs-Button sofort
        self.settings_button.setEnabled(True)
        
        # Entferne vorherigen Start-Button falls vorhanden
        if hasattr(self, 'start_game_button'):
            self.start_game_button.setParent(None)
            delattr(self, 'start_game_button')
        
        # Füge temporären Start-Button hinzu
        self.start_game_button = QPushButton("🚀 Spiel starten")
        self.start_game_button.clicked.connect(self.begin_game_loading)
        
        # Finde das control_group und füge den Button hinzu
        control_group = self.findChild(QGroupBox, "control_group")
        if not control_group:
            # Fallback: Finde über Layout
            for widget in self.findChildren(QGroupBox):
                if "Spielsteuerung" in widget.title():
                    control_group = widget
                    break
        
        if control_group:
            layout = control_group.layout()
            # Füge Start-Button vor dem Stretch hinzu
            layout.insertWidget(layout.count() - 1, self.start_game_button)

    def begin_game_loading(self):
        """Beginnt das eigentliche Laden des Spiels basierend auf den Einstellungen."""
        # Entferne den Start-Button
        if hasattr(self, 'start_game_button'):
            self.start_game_button.setParent(None)
            delattr(self, 'start_game_button')
        
        # Starte den entsprechenden Modus
        if self.is_cloud_mode():
            self.start_cloud_mode()
        else:
            self.start_offline_mode()

    def start_offline_mode(self):
        """Startet das Laden des lokalen KI-Modells."""
        logger.info('Starte Offline-Modus...')
        self.story_display.setHtml("""
        <div style='color: #dcdcaa; text-align: center; padding: 20px;'>
            <h3>🔧 Lade lokales KI-Modell...</h3>
            <p>Dies kann beim ersten Start einige Minuten dauern.</p>
        </div>
        """)
        
        try:
            self.inference_service = InferenceService()
            if not self.inference_service.base_model_loaded:
                self.on_model_load_error(self.inference_service.load_status)
                return
            self.on_model_loaded(self.inference_service)
        except Exception as e:
            self.on_model_load_error(str(e))

    def on_model_loaded(self, inference_service: InferenceService):
        """Wird aufgerufen, wenn das lokale Modell erfolgreich geladen wurde."""
        self.inference_service = inference_service
        self.game_manager = GameManager(self.inference_service)
        
        # Versuche ein Spiel zu starten oder zu laden (mit dem ausgewählten User)
        game_started = self.game_manager.start_or_load_game(self, user_id=self.current_user['user_id'])
        if game_started:
            initial_story = self.game_manager.get_initial_story_prompt()
            self.story_display.setHtml(f"<div>{initial_story}</div>")
            self.update_status_display()
            self.set_input_enabled(True)
        else:
            self.close()
    
    def on_model_load_error(self, error_message: str):
        """Wird aufgerufen, wenn das lokale Modell nicht geladen werden konnte."""
        QMessageBox.critical(self, "Fehler", 
                           f"Das KI-Modell konnte nicht geladen werden.\n\n{error_message}")
        self.close()

    def on_send_command(self):
        """Wird aufgerufen, wenn der Spieler einen Befehl sendet."""
        command = self.input_line.text().strip()
        if not command:
            return
        
        # Zeige den Spielerbefehl an
        self.story_display.append(f"""
        <div style='margin: 15px 0; padding: 10px; background-color: #2d2d30; border-left: 4px solid #9cdcfe; border-radius: 4px;'>
            <strong style='color: #9cdcfe;'>Du:</strong> {command}
        </div>
        """)
        
        self.input_line.clear()
        self.set_input_enabled(False)

        if self.game_manager:
            try:
                response = self.game_manager.process_player_command(command, self)
                self.process_ai_response(response)
            except Exception as e:
                logger.error(f"Fehler beim Verarbeiten des Befehls: {e}")

                self.process_ai_response("Ein unerwarteter Fehler ist aufgetreten. Bitte versuchen Sie es erneut.")

    def process_ai_response(self, response_text: str):
        """Zeigt die KI-Antwort im Story-Display an."""
        self.story_display.append(f"""
        <div style='margin: 15px 0; padding: 15px; background-color: #1e2a1e; border-left: 4px solid #4caf50; border-radius: 4px;'>
            {response_text}
        </div>
        """)
        
        # Scrolle zum Ende
        scrollbar = self.story_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        self.set_input_enabled(True)

    def set_input_enabled(self, enabled: bool):
        """Aktiviert oder deaktiviert die Eingabeelemente."""
        self.input_line.setEnabled(enabled)
        self.send_button.setEnabled(enabled)
        if enabled:
            self.input_line.setFocus()
    
    def on_correct_last_answer(self):
        """Öffnet den Korrektur-Dialog für die letzte Antwort."""
        if self.game_manager:
            self.game_manager.correct_last_narrative(self)
        else:
            QMessageBox.information(self, "Info", 
                                  "Kein aktives Spiel gefunden.")

    def on_save_game(self):
        """Speichert das aktuelle Spiel."""
        QMessageBox.information(self, "Info", 
                              "Offline-Spiele werden automatisch gespeichert.")

    def update_status_display(self):
        """Aktualisiert die Statusanzeige."""
        if self.game_manager and self.game_manager.game_state:
            char_info = self.game_manager.game_state.get("character_info", {})
            loc_info = self.game_manager.game_state.get("location_info", {})
            
            status_html = f"""
            <div style='padding: 10px;'>
                <h4 style='color: #569cd6; margin-bottom: 10px;'>📋 Charakterinfo</h4>
                <p><strong>Name:</strong> {char_info.get('name', 'N/A')}</p>
                <p><strong>Level:</strong> {char_info.get('level', 1)}</p>
                <p><strong>XP:</strong> {char_info.get('xp', 0)}</p>
                <p><strong>Ort:</strong> {loc_info.get('name', 'Unbekannt')}</p>
                
                <h4 style='color: #569cd6; margin: 15px 0 10px 0;'>⚔️ Attribute</h4>
            """
            
            attributes = char_info.get("attributes", {})
            for attr_name, attr_value in attributes.items():
                status_html += f"<p><strong>{attr_name}:</strong> {attr_value}</p>"
            
            status_html += "</div>"
            self.status_display.setHtml(status_html)
        else:
            self.status_display.setHtml("""
            <div style='padding: 10px; text-align: center; color: #888;'>
                <p>Status wird geladen...</p>
            </div>
            """)
    
    def load_settings(self):
        """Lädt die aktuellen Einstellungen."""
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
                    self.settings = json.load(f)
            except Exception as e:
                logger.error(f"Fehler beim Laden der Einstellungen: {e}")
                self.settings = default_settings
        else:
            self.settings = default_settings
    
    def is_cloud_mode(self) -> bool:
        """Prüft ob Cloud-Modus aktiviert ist."""
        if not self.settings:
            return False
        return self.settings.get('ki_service', {}).get('use_cloud', False)
    
    def start_cloud_mode(self):
        """Startet den Cloud-Modus mit API-Service."""
        logger.info('Starte Cloud-Modus...')
        self.story_display.setHtml("""
        <div style='color: #dcdcaa; text-align: center; padding: 20px;'>
            <h3>☁️ Verbinde mit Cloud-KI-Service...</h3>
            <p>Bitte warten, während die Verbindung hergestellt wird.</p>
        </div>
        """)
        
        try:
            cloud_settings = self.settings.get('ki_service', {}).get('cloud', {})
            service_url = cloud_settings.get('service_url', '')
            api_key_path = cloud_settings.get('api_key_path', '')
            
            if not service_url:
                self.on_cloud_service_error("Keine Service-URL konfiguriert. Bitte überprüfen Sie die Einstellungen.")
                return
            
            # Prüfe ob es sich um eine lokale URL handelt
            is_local = service_url.lower().startswith('http://127.0.0.1') or service_url.lower().startswith('http://localhost')
            
            if not is_local and (not api_key_path or not Path(api_key_path).exists()):
                self.on_cloud_service_error("API-Key-Datei für externe Cloud-API nicht gefunden. Bitte überprüfen Sie die Einstellungen.")
                return
            
            # Hier würde die echte Cloud-Service-Initialisierung stattfinden
            # Für jetzt simulieren wir einen funktionierenden Service
            if is_local:
                logger.info(f"Lokale API simuliert für URL: {service_url}")
            else:
                logger.info(f"Cloud-Service simuliert für URL: {service_url}")
            
            # Erstelle einen Mock-InferenceService für Cloud-Modus
            self.inference_service = self.create_mock_cloud_service()
            self.on_model_loaded(self.inference_service)
            
        except Exception as e:
            self.on_cloud_service_error(f"Fehler beim Verbinden mit Cloud-Service: {e}")
    
    def create_mock_cloud_service(self):
        """Erstellt einen echten Cloud-Service für die konfigurierte API."""
        try:
            cloud_settings = self.settings.get('ki_service', {}).get('cloud', {})
            service_url = cloud_settings.get('service_url', '')
            api_key_path = cloud_settings.get('api_key_path', '')
            timeout = cloud_settings.get('timeout', 30)
            
            # Setze Google Application Credentials falls verfügbar
            if api_key_path and Path(api_key_path).exists():
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = api_key_path
                logger.info(f"Google Application Credentials gesetzt: {api_key_path}")
            
            # Erstelle echten CloudInferenceService
            cloud_service = CloudInferenceService(
                service_url=service_url,
                api_key_path=api_key_path if api_key_path else None,
                timeout=timeout
            )
            
            # Teste die Verbindung (kann bei Google Cloud Run länger dauern)
            logger.info("Teste Cloud-Service Verbindung...")
            if 'run.app' in service_url.lower():
                logger.info("Google Cloud Run erkannt - Kaltstart kann bis zu 6 Minuten dauern...")
                
            if cloud_service.test_connection():
                logger.info(f"Cloud-Service erfolgreich verbunden: {service_url}")
                return cloud_service
            else:
                logger.warning("Cloud-Service Verbindungstest fehlgeschlagen, verwende lokalen Fallback")
                return InferenceService()
                
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Cloud-Service: {e}")
            # Fallback zum lokalen Service
            return InferenceService()
    
    def on_cloud_service_error(self, error_message: str):
        """Wird aufgerufen, wenn ein Fehler beim Cloud-Service auftritt."""
        logger.error(f"Cloud-Service Fehler: {error_message}")
        
        # Frage ob auf lokalen Modus zurückfallen soll
        reply = QMessageBox.question(
            self, 
            "Cloud-Service Fehler", 
            f"Fehler beim Cloud-Service:\n{error_message}\n\n"
            "Möchten Sie stattdessen den lokalen Offline-Modus verwenden?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Schalte temporär auf lokalen Modus um
            self.settings['ki_service']['use_cloud'] = False
            logger.info("Wechsle zu lokalem Modus...")
            self.start_offline_mode()
        else:
            self.close()
    
    def on_open_settings(self):
        """Öffnet den Einstellungsdialog."""
        logger.info("Öffne Einstellungsdialog...")
        
        settings = SettingsDialog.show_settings(self)
        if settings:
            logger.info("Einstellungen wurden geändert")
            old_mode = self.is_cloud_mode()
            self.settings = settings
            new_mode = self.is_cloud_mode()
            
            # Prüfe ob sich der Service-Modus geändert hat
            current_mode = "Cloud-API" if new_mode else "Lokale KI"
            
            if old_mode != new_mode:
                # Service-Modus hat sich geändert - Update UI
                self.setWindowTitle(f"Last-Strawberry - {self.current_user['username']} ({current_mode})")
                
                # Wenn wir noch nicht gestartet haben, update die Anzeige
                if hasattr(self, 'start_game_button'):
                    self.show_startup_options()
                else:
                    # Spiel läuft bereits - Neustart erforderlich
                    QMessageBox.information(
                        self, 
                        "Einstellungen gespeichert", 
                        f"Service-Modus geändert zu: {current_mode}\n\n"
                        "Starten Sie das Spiel neu, um die Änderungen zu übernehmen."
                    )
            else:
                QMessageBox.information(
                    self, 
                    "Einstellungen gespeichert", 
                    f"Einstellungen wurden gespeichert.\n"
                    f"Aktueller Modus: {current_mode}"
                )

    
    def closeEvent(self, event):
        """Stellt sicher, dass alle Ressourcen sauber freigegeben werden."""
        super().closeEvent(event)


def main():
    """Hauptfunktion, die die Anwendung startet."""
    logger.info('main() entry point reached.')
    app = QApplication(sys.argv)
    
    # Setze App-Metadaten
    app.setApplicationName("Last-Strawberry")
    app.setApplicationVersion("5.0")
    app.setOrganizationName("KI-Training")
    
    try:
        logger.info('Erstelle AdventureWindow...')
        window = AdventureWindow()
        window.show()
        logger.info('AdventureWindow erstellt und angezeigt.')
        sys.exit(app.exec())
    except Exception as e:
        logger.error(f"Fehler beim Starten der Anwendung: {e}", exc_info=True)
        QMessageBox.critical(None, "Startfehler", 
                           f"Die Anwendung konnte nicht gestartet werden:\n{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
