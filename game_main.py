# game_main.py
# -*- coding: utf-8 -*-

"""
Hauptanwendung für das 'Last-Strawberry' KI Text-Adventure.
Einstiegspunkt, der die UI erstellt und das Spiel startet.
VERSION 2: Robuste, ereignisgesteuerte Online-Logik.
"""

import sys
import logging
import asyncio
from typing import Optional, Coroutine, Dict, Any, Tuple

from PySide6.QtCore import QObject, Signal, QThread, Slot
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTextBrowser,
    QLineEdit, QHBoxLayout, QPushButton, QSplitter, QLabel, QMessageBox
)

# Passen Sie die Importpfade an Ihre finale Projektstruktur an
from class_folder.game_logic.game_manager import GameManager
from class_folder.core.inference_service import InferenceService
from class_folder.core.config_manager import ConfigManager
from class_folder.ui.settings_dialog import SettingsDialog
from class_folder.core.server_connector import ServerConnector
from class_folder.ui.mode_selection_dialog import ModeSelectionDialog
from class_folder.ui.login_dialog import LoginDialog
from class_folder.core.online_client import OnlineClient
from class_folder.ui.level_up_dialog import LevelUpDialog
from class_folder.ui.attribute_dialog import AttributeAllocationDialog
from class_folder.ui.setup_dialogs import CharacterCreationDialog, WorldCreationDialog, LoadGameDialog

# Logging-Konfiguration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

## NEU: Ein Worker, der asynchrone Aufgaben in einem Thread ausführt
class AsyncWorker(QObject):
    """Führt eine asynchrone Funktion in einem separaten Thread aus."""
    finished = Signal(object) # Signal mit dem Ergebnis der Aufgabe
    error = Signal(str)     # Signal im Fehlerfall

    def __init__(self, coro: Coroutine):
        super().__init__()
        self.coro = coro

    def run(self):
        try:
            result = asyncio.run(self.coro)
            self.finished.emit(result)
        except Exception as e:
            logger.error(f"Fehler im AsyncWorker: {e}", exc_info=True)
            self.error.emit(str(e))

class AdventureWindow(QMainWindow):
    """Das Hauptfenster für das Text-Abenteuer."""
    ## ENTFERNT: Die alte 'run_async' Helferfunktion wird nicht mehr benötigt.

    def __init__(self, game_mode: str = "offline"):
        super().__init__()
        self.setWindowTitle("Last-Strawberry - KI Text-Adventure")
        self.setGeometry(100, 100, 1200, 800)

        self.game_mode = game_mode
        self.config_manager = ConfigManager()
        self.server_connector: Optional[ServerConnector] = None
        self.game_manager: Optional[GameManager] = None
        self.inference_service: Optional[InferenceService] = None
        self.online_client: Optional[OnlineClient] = None
        self.thread: Optional[QThread] = None

        self.setup_ui()
        self.apply_stylesheet()
        
        # ## GEÄNDERT: Der Start wird direkt hier aufgerufen
        self.initialize_services_and_start_game()

    def setup_ui(self):
        """Erstellt und arrangiert die UI-Widgets."""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        splitter = QSplitter(self)
        
        # Linkes Panel
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        self.story_display = QTextBrowser()
        left_layout.addWidget(self.story_display)
        input_layout = QHBoxLayout()
        self.input_line = QLineEdit()
        self.send_button = QPushButton("Senden")
        input_layout.addWidget(self.input_line)
        input_layout.addWidget(self.send_button)
        left_layout.addLayout(input_layout)

        # Rechtes Panel
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.status_display = QTextBrowser()
        self.sync_button = QPushButton("Trainingsdaten senden")
        self.download_adapter_button = QPushButton("Neues KI-Modell prüfen")
        self.correct_button = QPushButton("Letzte Antwort korrigieren")
        self.settings_button = QPushButton("Einstellungen")
        
        right_layout.addWidget(QLabel("Charakter-Status"))
        right_layout.addWidget(self.status_display)
        right_layout.addWidget(QLabel("Server & KI-Management"))
        right_layout.addWidget(self.sync_button)
        right_layout.addWidget(self.download_adapter_button)
        right_layout.addWidget(self.correct_button)
        right_layout.addStretch()
        right_layout.addWidget(self.settings_button)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([800, 400])
        main_layout.addWidget(splitter)
        
        # Verbindungen
        self.send_button.clicked.connect(self.on_send_command)
        self.input_line.returnPressed.connect(self.on_send_command)
        self.correct_button.clicked.connect(self.on_correct_last_answer)
        self.settings_button.clicked.connect(self.on_open_settings)
        # Andere Button-Verbindungen werden bei Initialisierung gesetzt

    def apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #1e1e1e; color: #d4d4d4; }
            QTextBrowser { background-color: #1e1e1e; border: 1px solid #333; font-family: 'Consolas', monospace; font-size: 16px; padding: 10px; }
            QLineEdit { background-color: #2a2a2a; border: 1px solid #444; padding: 8px; font-size: 14px; border-radius: 4px; }
            QPushButton { background-color: #3c3c3c; border: 1px solid #555; padding: 8px 16px; border-radius: 4px; }
            QPushButton:hover { background-color: #4a4a4a; } QPushButton:pressed { background-color: #5a5a5a; }
            QPushButton:disabled { background-color: #2a2a2a; color: #555; }
            QDialog { background-color: #252526; } QLabel { font-weight: bold; }
        """)

    def initialize_services_and_start_game(self):
        """Leitet den Startprozess basierend auf dem gewählten Spielmodus ein."""
        if self.game_mode == "offline":
            # Offline-Modus ist temporär deaktiviert
            QMessageBox.warning(self, "Hinweis", "Offline-Modus ist temporär deaktiviert. Bitte verwenden Sie den Online-Modus.")
            self.close()
        elif self.game_mode == "online":
            # ## GEÄNDERT: Startet die ereignisgesteuerte Kette
            self.start_online_mode()
    
    def run_async_task(self, coro: Coroutine, on_finish_slot: Slot, on_error_slot: Slot):
        """Führt eine asynchrone Aufgabe sicher in einem Thread aus."""
        self.thread = QThread()
        worker = AsyncWorker(coro)
        worker.moveToThread(self.thread)
        
        worker.finished.connect(on_finish_slot)
        worker.error.connect(on_error_slot)
        
        worker.finished.connect(self.thread.quit)
        worker.finished.connect(worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.thread.start()
        # QThread.started Signal an den Worker Slot verbinden
        self.thread.started.connect(worker.run)


    # --- OFFLINE MODUS LOGIK ---
    def start_offline_mode(self):
        """Startet das Laden des lokalen KI-Modells."""
        self.story_display.setHtml("<p style='color: #dcdcaa;'>Lade lokales KI-Modell... Dies kann dauern.</p>")
        # Die Logik mit dem ModelLoaderWorker für den Offline-Modus ist gut und bleibt erhalten.
        # (Vollständigkeitshalber hier nicht erneut eingefügt)
        from class_folder.game_logic.game_manager import GameManager
        from class_folder.core.inference_service import InferenceService

        self.inference_service = InferenceService()
        if not self.inference_service.base_model_loaded:
             self.on_model_load_error(self.inference_service.load_status)
             return
        self.on_model_loaded(self.inference_service)

    def on_model_loaded(self, inference_service: InferenceService):
        self.inference_service = inference_service
        self.game_manager = GameManager(self.inference_service)
        game_started = self.game_manager.start_or_load_game(self)
        if game_started:
            self.story_display.setHtml(self.game_manager.get_initial_story_prompt())
            self.update_status_display()
        else: self.close()
        self.set_input_enabled(True)
    
    def on_model_load_error(self, error_message: str):
        QMessageBox.critical(self, "Fehler", f"Das KI-Modell konnte nicht geladen werden.\n\n{error_message}")
        self.close()

    # --- ONLINE MODUS LOGIK (NEU STRUKTURIERT) ---
    
    def start_online_mode(self):
        """Schritt 1: Zeigt den Login-Dialog an."""
        self.story_display.setHtml("<p style='color: #4ec9b0;'>Online-Modus. Bitte am Server anmelden...</p>")
        login_dialog = LoginDialog(self)
        if login_dialog.exec():
            username, password = login_dialog.get_credentials()
            if username and password:
                self.set_input_enabled(False)
                self.story_display.append("<p style='color: #dcdcaa;'>Verbinde und melde an...</p>")
                # Schritt 2: Führe den Login im Hintergrund aus
                coro = self._perform_login(username, password)
                self.run_async_task(coro, self.on_login_finished, self.on_online_error)
            else:
                QMessageBox.warning(self, "Fehler", "Benutzername und Passwort dürfen nicht leer sein.")
                self.close()
        else:
            self.close()

    async def _perform_login(self, username: str, password: str) -> bool:
        """Asynchrone Coroutine, die den Login durchführt."""
        try:
            SERVER_URL = "http://localhost:8001"
            self.online_client = OnlineClient(SERVER_URL)
            result = await self.online_client.login(username, password)
            logger.info(f"Login result: {result}")
            return result
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    @Slot(object)
    def on_login_finished(self, success: bool):
        """Schritt 3: Wird nach dem Login-Versuch aufgerufen."""
        if success:
            self.story_display.append("<p style='color: #569cd6;'>Anmeldung erfolgreich. Lade Welten...</p>")
            # Schritt 4: Lade die Welten im Hintergrund
            coro = self._fetch_worlds()
            self.run_async_task(coro, self.on_worlds_fetched, self.on_online_error)
        else:
            self.on_online_error("Anmeldung fehlgeschlagen. Bitte Zugangsdaten prüfen.")

    async def _fetch_worlds(self) -> list:
        """Asynchrone Coroutine, die die Welten vom Server holt."""
        return await self.online_client.get_worlds()

    @Slot(object)
    def on_worlds_fetched(self, worlds: list):
        """Schritt 5: Zeigt die Weltenauswahl an."""
        dialog = LoadGameDialog(worlds or [], self)
        if dialog.exec():
            selection = dialog.get_selection()
            if selection: # Bestehendes Spiel laden
                self.online_client.active_world_id = selection['world_id']
                self.online_client.active_player_id = selection['player_id']
                self.story_display.append("<p style='color: #dcdcaa;'>Lade Spielstand...</p>")
                coro = self.online_client.load_game_summary()
                self.run_async_task(coro, self.on_game_loaded, self.on_online_error)
            else: # Neues Spiel erstellen
                # Der Dialog-Flow für die Erstellung ist synchron und kann hier bleiben
                self.create_online_new_game()
        else:
            self.close()

    def create_online_new_game(self):
        """Synchroner Teil des Flows zur Erstellung eines neuen Online-Spiels."""
        world_dialog = WorldCreationDialog(self)
        if not world_dialog.exec(): self.close(); return
        world_data = world_dialog.get_data()

        char_dialog = CharacterCreationDialog(self)
        if not char_dialog.exec(): self.close(); return
        char_data = char_dialog.get_data()

        attr_dialog = AttributeAllocationDialog(self)
        if not attr_dialog.exec(): self.close(); return
        attributes = attr_dialog.get_attributes()

        if not all([world_data, char_data, attributes]): self.close(); return
        
        payload = {**world_data, **char_data, "attributes": attributes}
        self.story_display.append("<p style='color: #dcdcaa;'>Erstelle neue Welt auf dem Server...</p>")
        coro = self.online_client.create_world(payload)
        self.run_async_task(coro, self.on_world_created, self.on_online_error)

    @Slot(object)
    def on_world_created(self, response: dict):
        """Wird aufgerufen, nachdem der Server die neue Welt erstellt hat."""
        if response:
            self.online_client.active_world_id = response['world_id']
            self.online_client.active_player_id = response['player_id']
            self.on_game_loaded(response.get('initial_story', ''))
        else:
            self.on_online_error("Welt konnte nicht auf dem Server erstellt werden.")
            
    @Slot(object)
    def on_game_loaded(self, initial_text: str):
        """Wird aufgerufen, wenn das Spiel (neu oder geladen) bereit ist."""
        self.story_display.setHtml(f"<div>{initial_text}</div>")
        self.update_status_display()
        self.set_input_enabled(True)

    @Slot(str)
    def on_online_error(self, error_message: str):
        """Zentrale Fehlerbehandlung für den Online-Modus."""
        QMessageBox.critical(self, "Online-Fehler", error_message)
        self.set_input_enabled(True)
        # Optional: self.close() oder zum Login-Screen zurückkehren

    # --- Gemeinsame Logik ---
    
    def on_send_command(self):
        """Wird aufgerufen, wenn der Spieler einen Befehl sendet."""
        command = self.input_line.text().strip()
        if not command: return
        
        self.story_display.append(f"<p style='color: #9cdcfe;'><b>> {command}</b></p>")
        self.input_line.clear()
        self.set_input_enabled(False)

        if self.game_mode == "offline":
            response = self.game_manager.process_player_command(command, self)
            self.process_ai_response(response)
        elif self.game_mode == "online" and self.online_client:
            # ## GEÄNDERT: Nutzt den robusten Async-Task-Runner
            coro = self.online_client.send_command(command)
            self.run_async_task(coro, self.on_command_response, self.on_online_error)

    @Slot(object)
    def on_command_response(self, response_obj: dict):
        """Verarbeitet die Antwort vom Server nach einem Befehl."""
        if not response_obj:
            self.on_online_error("Keine gültige Antwort vom Server erhalten.")
            return

        # LEVEL UP Event behandeln
        if response_obj.get("event_type") == "LEVEL_UP":
            self.process_ai_response(response_obj.get("message", ""))
            self.handle_level_up_dialog(response_obj.get("data", {}))
        else:
            self.process_ai_response(response_obj.get("response", ""))
        
        self.update_status_display()
        self.set_input_enabled(True)
        
    def handle_level_up_dialog(self, level_up_data: dict):
        """Öffnet den Level-Up-Dialog (synchron) und sendet dann das Ergebnis."""
        dialog = LevelUpDialog(level_up_data.get("current_attributes", {}), level_up_data.get("points_to_spend", 0), self)
        if dialog.exec():
            new_attributes = dialog.get_new_attributes()
            self.story_display.append("<p style='color: #dcdcaa;'>Aktualisiere Attribute auf dem Server...</p>")
            coro = self.online_client.update_attributes(new_attributes)
            # Wir könnten hier einen weiteren Slot für das Ergebnis erstellen, aber für eine einfache
            # Erfolgs/Fehler-Meldung ist eine QMessageBox ausreichend.
            self.run_async_task(coro, lambda s: QMessageBox.information(self, "Erfolg", "Attribute aktualisiert!"), self.on_online_error)

    def process_ai_response(self, response_text: str):
        self.story_display.append(f"<div>{response_text}</div>")
        self.story_display.verticalScrollBar().setValue(self.story_display.verticalScrollBar().maximum())

    def set_input_enabled(self, enabled: bool):
        self.input_line.setEnabled(enabled)
        self.send_button.setEnabled(enabled)
        if enabled: self.input_line.setFocus()
    
    def on_correct_last_answer(self):
        if self.game_mode == 'offline' and self.game_manager:
            self.game_manager.correct_last_narrative(self)
        else:
            QMessageBox.information(self, "Info", "Diese Funktion ist derzeit nur im Offline-Modus verfügbar.")

    def update_status_display(self):
        """Aktualisiert die Statusanzeige (vereinfacht)."""
        # Diese Methode müsste für den Online-Modus den Zustand vom Server abfragen.
        # Wir lassen sie vorerst einfach, um den Fokus auf die Kernlogik zu legen.
        if self.game_mode == 'offline' and self.game_manager and self.game_manager.game_state:
            char_info = self.game_manager.game_state.get("character_info", {})
            self.status_display.setHtml(f"<p><b>Name:</b> {char_info.get('name', 'N/A')}</p>")
        else:
            self.status_display.setHtml("<p>Status wird vom Server verwaltet.</p>")

    def on_open_settings(self):
        """Öffnet den Einstellungsdialog."""
        # Diese Funktion bleibt unverändert
        pass
    
    def closeEvent(self, event):
        """Stellt sicher, dass der Client sauber herunterfährt."""
        if self.online_client:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self.online_client.close())
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    mode = ModeSelectionDialog.get_mode()
    if mode:
        window = AdventureWindow(game_mode=mode)
        window.show()
        sys.exit(app.exec())