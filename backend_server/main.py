# backend_server/main.py
# -*- coding: utf-8 -*-

"""
Dies ist der Haupt-Endpunkt für den Backend-Server. Er läuft auf dem Root-Server,
verwaltet die Spiellogik und kommuniziert mit dem KI-Dienst.
"""

import logging
import sys
import os
import certifi
import httpx
import json
import subprocess
import asyncio
import re
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from google.oauth2 import id_token
from google.auth.transport import requests

# Füge das Projektverzeichnis zum Python-Pfad hinzu
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware

# Wir importieren jetzt die neue Online-Version des GameManagers
from class_folder.game_logic.game_manager_online import GameManagerOnline
from class_folder.core.database_manager import DatabaseManager
from server_tools.auth_utils import verify_password, get_password_hash

ALLOWED_SCRIPTS = {
    "train_analyst": project_root / "trainer/train_analyst.py",
    "train_narrative": project_root / "trainer/train_narrative.py",
}

# --- Logging-Konfiguration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WorldCreationResponse(BaseModel):
    message: str
    world_id: int
    player_id: int
    initial_story: str

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_active_user(token: str = Depends(oauth2_scheme)):
    """
    Abhängigkeit, die den Benutzer aus dem Token holt und prüft, ob er aktiv ist.
    In unserem Fall ist der Token einfach der Benutzername.
    """
    user = db_manager.get_user_by_username(token)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Ungültige Authentifizierungsdaten",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.get('is_active'):
        raise HTTPException(status_code=400, detail="Inaktiver Benutzer")
    return user

# --- Konfiguration ---
AI_SERVICE_URL = "https://last-strawberry-ai-service-520324701590.europe-west4.run.app" # Die Adresse unseres Docker-Containers
# AI_SERVICE_URL = "http://127.0.0.1:8080"  # Lokaler Server für Entwicklung
# --- FastAPI App ---
key_path = project_root / "backend_server" / "key.json"
if key_path.exists():
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(key_path)

app = FastAPI(
    title="Last-Strawberry Backend Server",
    description="Verwaltet die Spiellogik und Benutzer.",
    version="1.3.0"
)
origins = [
    "*",  # Erlaubt alle Origins, für die Entwicklung am einfachsten.
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Erlaubt alle Methoden (GET, POST, etc.)
    allow_headers=["*"], # Erlaubt alle Header
)

# --- Globale Instanzen ---
# Diese werden beim Start der Anwendung initialisiert
game_manager_instance: Optional[GameManagerOnline] = None
db_manager = DatabaseManager()

# --- KI-Kommunikation ---
async def call_ai_service(prompt: str, world_name: str, adapter_type: str) -> str:
    """
    Ruft den externen KI-Dienst auf, inklusive einer robusten
    Retry-Logik, um Kaltstarts abzufangen.
    """
    if not AI_SERVICE_URL:
        return "[Fehler: Die AI_SERVICE_URL ist nicht konfiguriert.]"

    request_data = {"prompt": prompt, "world_name": world_name, "adapter_type": adapter_type}
    max_retries = 5
    retry_delay_seconds = 60 # 1 Minute zwischen den Versuchen

    # Timeout für einzelne Anfragen (z.B. Health-Check oder die eigentliche Anfrage)
    # Nicht zu verwechseln mit dem gesamten Timeout über alle Retries.
    timeout_config = httpx.Timeout(45.0) 
    ssl_context = httpx.create_ssl_context(verify=certifi.where())

    for attempt in range(max_retries):
        try:
            logger.info(f"Versuch {attempt + 1}/{max_retries}: KI-Dienst wird kontaktiert...")
            async with httpx.AsyncClient(timeout=timeout_config, verify=ssl_context) as client:
                
                # Schritt 1: Sende einen leichten "Ping" an den /health Endpunkt.
                # Dies allein kann den Kaltstart auslösen.
                health_response = await client.get(f"{AI_SERVICE_URL}/health")
                
                # Wir prüfen nicht mal die Antwort, die Anfrage allein reicht als Weckruf.
                # Jetzt, wo der Dienst (hoffentlich) warm ist, senden wir die echte Anfrage.
                logger.info("Health-Ping gesendet. Sende jetzt die Hauptanfrage...")
                
                # Erhöhe das Timeout für die eigentliche Generate-Anfrage, da diese länger dauern kann.
                generate_timeout = httpx.Timeout(300.0)
                response = await client.post(f"{AI_SERVICE_URL}/generate", json=request_data, timeout=generate_timeout)
                
                response.raise_for_status() # Löst bei 4xx/5xx Fehlern eine Ausnahme aus
                
                logger.info("Erfolgreiche Antwort vom KI-Dienst erhalten.")
                return response.json()["generated_text"]

        except httpx.RequestError as e:
            logger.warning(f"Versuch {attempt + 1} fehlgeschlagen (RequestError): {e}. Warte {retry_delay_seconds}s...")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay_seconds)
            else:
                logger.error("Maximale Anzahl an Wiederholungen erreicht. KI-Dienst konnte nicht gestartet werden.")
                return f"[Fehler: Der KI-Dienst unter {AI_SERVICE_URL} konnte auch nach {max_retries} Versuchen nicht gestartet werden.]"
        except httpx.HTTPStatusError as e:
             logger.error(f"HTTP-Fehler vom KI-Dienst: {e.response.status_code} - {e.response.text}")
             return f"[Fehler: Der KI-Dienst hat einen Fehler gemeldet: {e.response.status_code}]"
    
    # Fallback, falls die Schleife ohne Rückgabe endet
    return "[Fehler: Unbekanntes Problem bei der Kommunikation mit dem KI-Dienst.]"

async def get_google_auth_token():
    """Holt ein gültiges ID-Token für die Anfrage an den Cloud Run Dienst."""
    try:
        auth_req = requests.Request()
        # Die `id_token.fetch_id_token` Funktion liest automatisch die
        # GOOGLE_APPLICATION_CREDENTIALS Umgebungsvariable.
        identity_token = id_token.fetch_id_token(auth_req, AI_SERVICE_URL)
        return identity_token
    except Exception as e:
        logger.error(f"Konnte kein Google Auth ID-Token erstellen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Authentifizierung für KI-Dienst fehlgeschlagen.")

async def call_ai_service(prompt: str, world_name: str, adapter_type: str) -> str:
    """Sendet eine authentifizierte Anfrage an den geschützten KI-Dienst."""
    request_data = {"prompt": prompt, "world_name": world_name, "adapter_type": adapter_type}
    
    try:
        # Hole ein frisches Authentifizierungs-Token für diese Anfrage
        token = await get_google_auth_token()
        headers = {'Authorization': f'Bearer {token}'}

        timeout_config = httpx.Timeout(300.0)
        
        # Wir benötigen hier keinen eigenen SSL-Kontext mehr, da Google's Auth-Bibliothek dies managed.
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            response = await client.post(f"{AI_SERVICE_URL}/generate", json=request_data, headers=headers)
            response.raise_for_status()
            return response.json()["generated_text"]
    except httpx.TimeoutException:
        return "[Fehler: Die KI hat zu lange für eine Antwort gebraucht.]"
    except httpx.RequestError as e:
        return f"[Fehler: Der KI-Dienst unter {AI_SERVICE_URL} ist nicht erreichbar: {e}]"
    except Exception as e:
        return "[Ein unerwarteter interner Fehler ist bei der KI-Kommunikation aufgetreten.]"

@app.on_event("startup")
def startup_event():
    """Initialisiert den GameManager beim Start des Servers."""
    global game_manager_instance
    game_manager_instance = GameManagerOnline(ai_caller=call_ai_service)
    logger.info("Backend-Server gestartet und GameManagerOnline initialisiert.")

# --- Login-System (Platzhalter) ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """Holt den Benutzer aus der DB basierend auf dem Token (hier: Benutzername)."""
    user = db_manager.get_user_by_username(token)
    if not user or not user.get('is_active', False):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials or inactive user")
    if not user.get('is_active', False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return user

def get_current_admin_user(current_user: dict = Depends(get_current_active_user)):
    if "admin" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Keine Berechtigung für diese Aktion")
    return current_user

@app.post("/token", tags=["Auth"])
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Überprüft Benutzerdaten gegen die DB und gibt einen Token zurück."""
    user = db_manager.get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    if not user.get('is_active', False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    
    # Der "Token" ist hier einfach der Benutzername. Für mehr Sicherheit verwendet man JWTs.
    return {"access_token": user["username"], "token_type": "bearer", "roles": user.get("roles", [])}

# --- Admin-Bereich: Benutzerverwaltung (NEU) ---

class UserCreate(BaseModel):
    username: str
    password: str
    roles: List[str] = ["gamemaster"]

class PasswordChange(BaseModel):
    new_password: str

class RolesChange(BaseModel):
    roles: List[str]

class UserUpdateRequest(BaseModel):
    password: Optional[str] = None
    roles: Optional[List[str]] = None

async def get_admin_user(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Stellt sicher, dass der aktuelle Benutzer ein Admin ist."""
    if "admin" not in current_user.get("roles", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin rights required")
    return current_user

@app.get("/admin/users", response_model=List[Dict[str, Any]], tags=["Admin - Users"])
async def list_users(admin: Dict[str, Any] = Depends(get_admin_user)):
    """Listet alle Benutzer auf (nur für Admins)."""
    return db_manager.get_all_users()

@app.get("/admin/users", dependencies=[Depends(get_current_admin_user)])
def get_all_users():
    return db_manager.get_all_users()

@app.post("/admin/users", dependencies=[Depends(get_current_admin_user)])
def create_new_user(user_data: dict): # Vereinfacht für JS
    user_id = db_manager.create_user(
        username=user_data['username'],
        hashed_password=get_password_hash(user_data['password']),
        roles=user_data['roles']
    )
    if not user_id:
        raise HTTPException(status_code=400, detail="Benutzer konnte nicht erstellt werden")
    return {"message": "Benutzer erfolgreich erstellt", "user_id": user_id}

@app.put("/admin/users/{user_id}", dependencies=[Depends(get_current_admin_user)])
def update_user_details(user_id: int, request: UserUpdateRequest):
    if request.password:
        db_manager.update_user_password(user_id, get_password_hash(request.password))
    if request.roles is not None and user_id != 1: # Schütze Rollen von User 1
        db_manager.update_user_roles(user_id, request.roles)
    return {"message": f"Benutzer {user_id} aktualisiert"}


@app.put("/admin/users/{user_id}/password", tags=["Admin - Users"])
async def change_user_password(user_id: int, password_data: PasswordChange, admin: Dict[str, Any] = Depends(get_admin_user)):
    """Ändert das Passwort eines Benutzers (nur für Admins)."""
    if user_id == 1 and admin['user_id'] != 1:
        raise HTTPException(status_code=403, detail="Only UserID=1 can change their own password.")
    if user_id != admin['user_id'] and admin['user_id'] != 1:
        raise HTTPException(status_code=403, detail="Permission denied.")

    hashed_password = get_password_hash(password_data.new_password)
    success = db_manager.update_user_password(user_id, hashed_password)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Password updated successfully"}

@app.put("/admin/users/{user_id}/roles", tags=["Admin - Users"])
async def change_user_roles(user_id: int, roles_data: RolesChange, admin: Dict[str, Any] = Depends(get_admin_user)):
    """Ändert die Rollen eines Benutzers (nur für Admins)."""
    if user_id == 1:
        raise HTTPException(status_code=403, detail="Cannot change roles for UserID=1.")
    success = db_manager.update_user_roles(user_id, roles_data.roles)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Roles updated successfully"}

@app.put("/admin/users/{user_id}/status", tags=["Admin - Users"])
async def change_user_status(user_id: int, is_active: bool, admin: Dict[str, Any] = Depends(get_admin_user)):
    """Aktiviert oder deaktiviert einen Benutzer (nur für Admins)."""
    if user_id == 1:
        raise HTTPException(status_code=403, detail="Cannot deactivate UserID=1.")
    success = db_manager.update_user_status(user_id, is_active)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": f"User status set to {'active' if is_active else 'inactive'}"}
    
def safe_world_name(world_name: str) -> str:
    # Erlaubt: Buchstaben, Zahlen, Bindestrich, Unterstrich, Leerzeichen, Umlaute, keine Steuerzeichen
    if not re.fullmatch(r"[A-Za-z0-9 _\-äöüÄÖÜß]+", world_name):
        raise ValueError("Ungültige Zeichen im Welt-Namen")
    if any(c in world_name for c in '\n\r"\'`$\\|&;'):
        raise ValueError("Ungültige Zeichen (Control Chars/Sonderzeichen) im Welt-Namen")
    return world_name
    
def run_script_in_background(allowed_key: str, world_id: int = None, world_name: str = None):
    """Führt ein zugelassenes Python-Skript im Hintergrund aus."""
    if allowed_key not in ALLOWED_SCRIPTS:
        logger.error(f"Unzulässiger Skriptname: {allowed_key}")
        return False

    script_path = ALLOWED_SCRIPTS[allowed_key]
    if not script_path.exists():
        logger.error(f"Skript nicht gefunden: {script_path}")
        return False

    if allowed_key == "train_narrative":
        if not isinstance(world_id, int) or world_id <= 0:
            logger.error("Ungültige world_id")
            return False
        if not re.fullmatch(r"[A-Za-z0-9 _\-äöüÄÖÜß]+", world_name):
            logger.error("Ungültiger world_name")
            return False
        args =  args = [str(world_id), safe_world_name(world_name)]
    else:
        args = []
    try:
        command = [sys.executable, str(script_path)] + args
        logger.info(f"Führe Befehl aus: {' '.join(command)}")
        # codeql[command-injection-prevented]: world_id und world_name werden strikt validiert (world_id muss positive Ganzzahl sein, world_name nur erlaubte Zeichen). subprocess wird NICHT mit shell=True verwendet, keine Shell-Expansion möglich.
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True  # Optional: fully detach on Unix
        )
        logger.info(f"Script gestartet mit PID {process.pid}")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Starten des Skripts '{script_path}': {e}", exc_info=True)
        return False

@app.post("/admin/train_analysis", dependencies=[Depends(get_current_admin_user)])
def trigger_train_analysis():
    success = run_script_in_background("train_analyst")
    if not success:
        raise HTTPException(status_code=500, detail="Das Analyse-Trainingsskript konnte nicht gestartet werden.")
        
    return {"message": "Analyse-Training wurde im Hintergrund gestartet. Überprüfe die Server-Logs für Details."}

@app.post("/admin/train_narrative/{world_id}", dependencies=[Depends(get_current_admin_user)])
def trigger_train_narrative(world_id: int, world_name: str):
    if not isinstance(world_id, int) or world_id <= 0:
        raise HTTPException(status_code=400, detail="world_id muss eine positive Ganzzahl sein.")
    if not re.fullmatch(r"[A-Za-z0-9 _\-äöüÄÖÜß]+", world_name):
        raise HTTPException(status_code=400, detail="world_name enthält ungültige Zeichen.")
    success = run_script_in_background("train_narrative", world_id, world_name)
    if not success:
        raise HTTPException(status_code=500, detail="Das Erzähl-Trainingsskript konnte nicht gestartet werden.")

    return {"message": f"Erzähl-Training für Welt '{world_name}' wurde im Hintergrund gestartet."}

class CorrectionRequest(BaseModel):
    event_id: int
    corrected_text: str
    corrected_commands: List[Dict[str, Any]]

@app.get("/events/last")
def get_last_event_for_correction(world_id: int, current_user: dict = Depends(get_current_active_user)):
    # Annahme: GameMaster dürfen korrigieren
    if "gamemaster" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    event = db_manager.get_last_event_details(world_id)
    if not event:
        raise HTTPException(status_code=404, detail="Kein Event für diese Welt gefunden")
    # Stelle sicher, dass JSON als Objekt und nicht als String zurückgegeben wird
    try:
        event['extracted_commands_json'] = json.loads(event['extracted_commands_json'])
    except (json.JSONDecodeError, TypeError):
        event['extracted_commands_json'] = []
    return event

class CorrectionRequest(BaseModel):
    event_id: int
    corrected_text: str
    corrected_commands: List[Dict[str, Any]]

@app.post("/events/correct")
def save_event_correction(request: CorrectionRequest, current_user: dict = Depends(get_current_active_user)):
    if "gamemaster" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    success = db_manager.update_event_correction(
        event_id=request.event_id,
        corrected_text=request.corrected_text,
        corrected_commands=request.corrected_commands
    )
    if not success:
        raise HTTPException(status_code=500, detail="Event konnte nicht in der DB aktualisiert werden")
    return {"message": "Korrektur erfolgreich als Trainingsdatenpunkt gespeichert."}

class WorldCreateRequest(BaseModel):
    world_name: str
    lore: str
    char_name: str
    backstory: str
    attributes: Dict[str, int] 
    template_key: str = "system_fantasy"

@app.get("/worlds")
async def get_user_worlds(current_user: dict = Depends(get_current_user)):
    """Gibt eine Liste aller existierenden Welten zurück."""
    worlds = db_manager.get_all_worlds_and_players()
    return {"worlds": worlds}

@app.post("/worlds/create", response_model=WorldCreationResponse, dependencies=[Depends(get_current_active_user)])
async def create_new_world(request: WorldCreateRequest):
    """Erstellt eine neue Welt und einen Spielercharakter."""
    logger.info(f"Anfrage zur Welterstellung für '{request.world_name}' erhalten.")
    try:
        # 1. Startbedingungen von der KI generieren lassen
        initial_conditions = await game_manager_instance._generate_initial_conditions(
            world_lore=request.lore,
            char_backstory=request.backstory
        )
        if not initial_conditions:
            raise HTTPException(status_code=500, detail="KI konnte keine validen Startbedingungen erstellen.")

        # 2. Welt und Spieler in der DB anlegen
        new_ids = db_manager.create_world_and_player(
            world_name=request.world_name,
            lore=request.lore,
            template_key='system_fantasy', # Später dynamisch machen
            char_name=request.char_name,
            backstory=request.backstory,
            char_attributes=request.attributes,
            initial_location_name=initial_conditions['location_name'],
            initial_location_desc=initial_conditions['location_description'],
            initial_state_dict=initial_conditions['initial_state']
        )
        if not new_ids:
            raise HTTPException(status_code=500, detail="Fehler beim Speichern der neuen Welt in der Datenbank.")

        # 3. Spielzustand für die neue Welt laden
        game_manager_instance._load_game_state(new_ids['world_id'], new_ids['player_id'])
        game_manager_instance.is_new_game = True

        # 4. Initiale Story generieren
        initial_story_response = await game_manager_instance.get_initial_story_prompt()

        # KORREKTUR: Extrahiere den eigentlichen Text aus dem Antwort-Objekt.
        initial_story_text = initial_story_response.get("response", "[Fehler: Initialer Story-Text konnte nicht generiert werden.]")

        return {
            "message": "Welt erfolgreich erstellt",
            "world_id": new_ids['world_id'],
            "player_id": new_ids['player_id'],
            # KORREKTUR: Übergib hier den reinen Text an den Client.
            "initial_story": initial_story_text
        }
    except Exception as e:
        logger.error(f"Fehler bei der Welterstellung: {e}", exc_info=True)

# --- API-Endpunkte für das Spiel ---

class CommandRequest(BaseModel):
    command: str
    world_id: int
    player_id: int

@app.post("/command", tags=["Game"])
async def process_command(request: CommandRequest, current_user: dict = Depends(get_current_user)):
    """Nimmt einen Spieler-Befehl entgegen und gibt die Antwort des Spiels zurück."""
    if not game_manager_instance:
        raise HTTPException(status_code=503, detail="GameManager ist nicht initialisiert.")
    
    game_manager_instance._load_game_state(request.world_id, request.player_id)
    response_text = await game_manager_instance.process_player_command(request.command)
    
    return response_text

@app.get("/load_game_summary")
async def load_game_summary(world_id: int, player_id: int, current_user: dict = Depends(get_current_user)):
    """Gibt die Start-Zusammenfassung für das Spiel des eingeloggten Benutzers zurück."""
    if not game_manager_instance:
        raise HTTPException(status_code=503, detail="GameManager ist nicht initialisiert.")

    game_manager_instance._load_game_state(world_id, player_id)
    game_manager_instance.is_new_game = False
    
    summary = await game_manager_instance.get_load_game_summary()
    return {"response": summary}


@app.get("/health")
async def root_health_check():
    # Prüfe auch die Verbindung zum KI-Dienst
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{AI_SERVICE_URL}/health")
            response.raise_for_status()
            ai_status = response.json()
    except httpx.RequestError:
        ai_status = {"status": "unreachable"}

    return {"status": "ok", "service": "Backend Server", "ai_service_status": ai_status}

class AttributeUpdateRequest(BaseModel):
    player_id: int
    new_attributes: Dict[str, int]

@app.post("/character/update_attributes", tags=["Game"])
async def update_attributes(request: AttributeUpdateRequest, current_user: dict = Depends(get_current_user)):
    """Speichert die vom Spieler nach einem Level-Up verteilten Attributspunkte."""
    # Sicherheitsprüfung: Darf dieser Benutzer diesen Charakter bearbeiten?
    # (In einer echten App wäre diese Logik komplexer)
    if request.player_id != current_user.get("player_id"):
        raise HTTPException(status_code=403, detail="Permission denied")

    success = db_manager.update_character_attributes(request.player_id, request.new_attributes)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update attributes in database.")
    
    return {"message": "Attributes updated successfully."}
# Um diesen Server lokal zu testen, führen Sie im Terminal aus:
# uvicorn backend_server.main:app --reload --port 8001
