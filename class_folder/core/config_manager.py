# class_folder/core/config_manager.py
# -*- coding: utf-8 -*-

"""
Verwaltet das Laden und Speichern von Konfigurationen (Server-URL, API-Key).
Verschlüsselt sensible Daten vor dem Speichern.
"""

import json
import logging
from pathlib import Path
from typing import Tuple, Optional

try:
    from cryptography.fernet import Fernet
except ImportError:
    # Fallback, falls die Bibliothek nicht installiert ist
    Fernet = None

logger = logging.getLogger(__name__)

class ConfigManager:
    """Verwaltet das sichere Speichern und Laden von App-Einstellungen."""

    def __init__(self, config_path: Path = Path("settings.json"), key_path: Path = Path("secret.key")):
        if not Fernet:
            raise ImportError("Die 'cryptography' Bibliothek wird benötigt. Bitte installieren mit: pip install cryptography")

        self.config_path = config_path
        self.key_path = key_path
        self.cipher_suite = self._load_or_generate_key()

    def _load_or_generate_key(self) -> Fernet:
        """Lädt den Verschlüsselungsschlüssel oder generiert einen neuen."""
        if not self.key_path.exists():
            logger.info("Kein Schlüssel gefunden. Generiere einen neuen Verschlüsselungsschlüssel...")
            key = Fernet.generate_key()
            with open(self.key_path, "wb") as key_file:
                key_file.write(key)
        else:
            with open(self.key_path, "rb") as key_file:
                key = key_file.read()
        
        return Fernet(key)

    def save_config(self, server_url: str, api_key: str):
        """
        Speichert die Konfiguration und verschlüsselt den API-Key.
        """
        try:
            # Den API-Key verschlüsseln
            encrypted_api_key = self.cipher_suite.encrypt(api_key.encode('utf-8'))
            
            config_data = {
                "server_url": server_url,
                "api_key_encrypted": encrypted_api_key.decode('utf-8')
            }
            
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4)
            logger.info(f"Konfiguration wurde erfolgreich in '{self.config_path}' gespeichert.")

        except Exception as e:
            logger.error(f"Fehler beim Speichern der Konfiguration: {e}", exc_info=True)

    def load_config(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Lädt die Konfiguration und entschlüsselt den API-Key.
        Gibt (None, None) zurück, wenn keine Konfiguration existiert.
        """
        if not self.config_path.exists():
            return None, None
            
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            server_url = config_data.get("server_url")
            encrypted_api_key = config_data.get("api_key_encrypted")
            
            if not encrypted_api_key:
                return server_url, None

            # Den API-Key entschlüsseln
            decrypted_api_key = self.cipher_suite.decrypt(encrypted_api_key.encode('utf-8')).decode('utf-8')
            
            return server_url, decrypted_api_key

        except (json.JSONDecodeError, FileNotFoundError):
            return None, None
        except Exception as e:
            logger.error(f"Fehler beim Laden oder Entschlüsseln der Konfiguration: {e}. Eventuell ist der Schlüssel ('{self.key_path}') nicht mehr gültig.", exc_info=True)
            return None, None