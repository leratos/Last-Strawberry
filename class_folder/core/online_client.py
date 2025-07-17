# class_folder/core/online_client.py
# -*- coding: utf-8 -*-

"""
Dieser Client kapselt die gesamte Kommunikation mit dem Backend-Server.
"""

import logging
from typing import Optional, Dict, Any, List
import httpx
import certifi

logger = logging.getLogger(__name__)

class OnlineClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        ssl_context = httpx.create_ssl_context(verify=certifi.where())
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=310.0, verify=ssl_context)
        self.token: Optional[str] = None
        self.user_id: Optional[int] = None
        self.roles: List[str] = []
        self.active_world_id: Optional[int] = None
        self.active_player_id: Optional[int] = None

    async def login(self, username: str, password: str) -> bool:
        """Versucht, sich am Server anzumelden und den Token/Rollen zu speichern."""
        try:
            response = await self.client.post("/token", data={"username": username, "password": password})
            response.raise_for_status()
            data = response.json()
            self.token = data.get("access_token")
            self.user_id = data.get("user_id")
            self.roles = data.get("roles", [])
            logger.info(f"Erfolgreich als '{username}' angemeldet. Rollen: {self.roles}")
            return True
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error(f"Login fehlgeschlagen: {e}")
            return False

    async def get_worlds(self) -> Optional[List[Dict[str, Any]]]:
        """Holt die Liste der verfügbaren Welten vom Server."""
        if not self.token: return None
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            response = await self.client.get("/worlds", headers=headers)
            response.raise_for_status()
            return response.json().get("worlds")
        except (httpx.RequestError, httpx.HTTPStatusError):
            return None

    async def create_world(self, world_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Sendet Daten zur Erstellung einer neuen Welt an den Server."""
        if not self.token: return None
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        try:
            response = await self.client.post("/worlds/create", json=world_data, headers=headers)
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError):
            return None

    async def send_command(self, command: str) -> Optional[Dict[str, Any]]:
        """Sendet einen Spieler-Befehl an den Server."""
        if not all([self.token, self.active_world_id, self.active_player_id]):
            return {"event_type": "ERROR", "response": "[Fehler: Kein aktives Spiel ausgewählt.]"}
        
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {"command": command, "world_id": self.active_world_id, "player_id": self.active_player_id}
        try:
            response = await self.client.post("/command", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"event_type": "ERROR", "response": f"[Server-Fehler: {e}]"}

    async def load_game_summary(self) -> Optional[str]:
        """Lädt die anfängliche Spielzusammenfassung vom Server."""
        if not all([self.token, self.active_world_id, self.active_player_id]):
            return "[Fehler: Kein aktives Spiel ausgewählt.]"
        
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"world_id": self.active_world_id, "player_id": self.active_player_id}
        try:
            response = await self.client.get("/load_game_summary", headers=headers, params=params)
            response.raise_for_status()
            return response.json().get("response")
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return f"[Server-Fehler: {e}]"
            
    async def update_attributes(self, new_attributes: Dict[str, int]) -> bool:
        """Sendet die aktualisierten Attribute an den Server."""
        if not all([self.token, self.active_player_id]): return False
        
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {"player_id": self.active_player_id, "new_attributes": new_attributes}
        try:
            response = await self.client.post("/character/update_attributes", json=payload, headers=headers)
            response.raise_for_status()
            return True
        except httpx.RequestError:
            return False

    async def close(self):
        await self.client.aclose()
