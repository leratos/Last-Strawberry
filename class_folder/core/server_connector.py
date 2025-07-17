# class_folder/core/server_connector.py (Finale, korrigierte Version)

import logging
import requests
import zipfile
import io
import json
import re
import shutil
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class ServerConnector:
    """Verwaltet API-Aufrufe an den zentralen Server für den Datenaustausch."""

    def __init__(self, base_url: str, api_token: str):
        """
        Initialisiert den Connector.

        Args:
            base_url (str): Die Basis-URL des FastAPI-Servers.
            api_token (str): Der API-Schlüssel für die Authentifizierung.
        """
        self.base_url = base_url.rstrip('/')
        # Der Header-Name muss exakt "X-API-Key" sein, wie vom Server erwartet.
        self.headers = {"X-API-Key": api_token}
        logger.info(f"ServerConnector initialisiert für URL: {self.base_url}")

    def _sanitize_name(self, name: str) -> str:
        """Bereinigt einen String, um ihn URL- und Dateisystem-sicher zu machen."""
        if not name: return ""
        s = name.lower().strip()
        s = re.sub(r'[\s\.]+', '_', s)
        s = re.sub(r'[^\w-]', '', s)
        s = re.sub(r'__+', '_', s)
        return s

    def upload_training_data(self, world_name: str, events: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Lädt bewertete Events als Datei zum generischen Server-Endpunkt hoch.
        Gibt (Erfolg, Nachricht) zurück.
        """
        if not events:
            return True, "Keine neuen Daten zum Senden vorhanden."

        sanitized_world_name = self._sanitize_name(world_name)
        if not sanitized_world_name:
            return False, "Welt-Name ist nach Bereinigung ungültig."

        # KORREKTE, GENERISCHE URL wird hier aufgebaut
        url = f"{self.base_url}/data/upload/{sanitized_world_name}"
        
        try:
            events_jsonl_string = "\n".join(json.dumps(e) for e in events)
            events_bytes = io.BytesIO(events_jsonl_string.encode('utf-8'))

            files = {'batch_file': (f'{sanitized_world_name}_batch.jsonl', events_bytes, 'application/jsonl')}
            
            logger.info(f"Sende {len(events)} Events für Welt '{world_name}' an URL: {url}")
            response = requests.post(url, files=files, headers=self.headers, timeout=120)
            
            response.raise_for_status() 

            response_data = response.json()
            msg = response_data.get("message", "Upload erfolgreich.")
            logger.info(f"Upload erfolgreich: {msg}")
            return True, msg

        except requests.exceptions.HTTPError as http_err:
            error_detail = f"Server antwortete mit Status {http_err.response.status_code}."
            try:
                server_msg = http_err.response.json().get("detail", "Keine weiteren Details.")
                error_detail += f" Nachricht: '{server_msg}'"
            except json.JSONDecodeError:
                error_detail += " Konnte Server-Antwort nicht als JSON parsen."
            
            logger.error(f"HTTP-Fehler beim Upload: {error_detail}", exc_info=False)
            return False, f"Fehler beim Upload. {error_detail}"
            
        except requests.exceptions.RequestException as req_err:
            msg = f"Netzwerkfehler: Konnte den Server unter {self.base_url} nicht erreichen."
            logger.error(f"{msg}: {req_err}", exc_info=True)
            return False, msg
        except Exception as e:
            msg = f"Ein unerwarteter Fehler ist aufgetreten: {e}"
            logger.error(msg, exc_info=True)
            return False, msg

    def download_latest_adapter(self, world_name: str, target_dir: Path) -> Tuple[Optional[Path], str]:
        """Lädt den neuesten Adapter für ein spezifisches Projekt herunter."""
        sanitized_world_name = self._sanitize_name(world_name)
        if not sanitized_world_name:
            return None, "Welt-Name ist nach Bereinigung ungültig."

        url = f"{self.base_url}/models/download/latest/{sanitized_world_name}"
        
        try:
            logger.info(f"Frage neuesten Adapter für Welt '{world_name}' von {url} an...")
            response = requests.get(url, headers=self.headers, timeout=180, stream=True)
            response.raise_for_status()

            content_disposition = response.headers.get('content-disposition')
            if not content_disposition:
                return None, "Fehler: Server hat keinen Dateinamen für den Adapter gesendet."

            adapter_zip_name_match = re.search('filename="?([^"]+)"?', content_disposition)
            if not adapter_zip_name_match:
                 return None, "Fehler: Konnte Dateinamen nicht aus Server-Antwort extrahieren."
            
            adapter_zip_name = adapter_zip_name_match.group(1)
            final_adapter_dir = target_dir / Path(adapter_zip_name).stem
            output_path = target_dir / sanitized_world_name

            if final_adapter_dir.exists():
                shutil.rmtree(final_adapter_dir)

            logger.info(f"Lade neue Adapter-Version '{adapter_zip_name}' herunter nach '{final_adapter_dir}'...")
            
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                z.extractall(final_adapter_dir)
            
            msg = f"Adapter '{final_adapter_dir.name}' erfolgreich heruntergeladen und entpackt."
            logger.info(msg)
            return True, msg
            
        except requests.exceptions.HTTPError as e:
            error_detail = f"Server antwortete mit Status {e.response.status_code}."
            try:
                server_msg = e.response.json().get("detail", "Keine weiteren Details.")
                error_detail += f" Nachricht: '{server_msg}'"
            except json.JSONDecodeError:
                pass
            logger.error(f"HTTP-Fehler beim Download: {error_detail}", exc_info=False)
            return None, f"Fehler beim Download. {error_detail}"
        except requests.exceptions.RequestException as e:
            msg = f"Netzwerkfehler beim Download: {e}"
            logger.error(msg, exc_info=True)
            return None, msg
        except Exception as e:
            msg = f"Unerwarteter Fehler beim Download: {e}"
            logger.error(msg, exc_info=True)
            return False, msg

