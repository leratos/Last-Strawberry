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
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from google.oauth2 import id_token
from google.auth.transport import requests

# Füge das Projektverzeichnis zum Python-Pfad hinzu
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

# Wir importieren jetzt die neue Online-Version des GameManagers
from class_folder.game_logic.game_manager_online import GameManagerOnline
from class_folder.core.database_manager import DatabaseManager
from server_tools.auth_utils import verify_password, get_password_hash, create_access_token, verify_access_token, get_current_user_from_token

ALLOWED_SCRIPTS = {
    "train_analyst": project_root / "trainer/train_analyst.py",
    "train_narrative": project_root / "trainer/train_narrative.py",
}

# --- Logging-Konfiguration ---
# Bestimme Log-Pfad je nach Umgebung
if os.path.exists("/var/www/vhosts/last-strawberry.com/last-strawberry-backend/logs/"):
    # Produktionsserver-Pfad
    log_path = "/var/www/vhosts/last-strawberry.com/last-strawberry-backend/logs/backend.log"
    access_log_path = "/var/www/vhosts/last-strawberry.com/last-strawberry-backend/logs/access.log"
else:
    # Lokaler Entwicklungspfad
    log_path = project_root / "backend_server" / "backend.log"
    access_log_path = project_root / "backend_server" / "access.log"

# Erstelle File-Handler für Backend-Logs
file_handler = logging.FileHandler(log_path, encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# Erstelle separaten Handler für Access-Logs (Login-Versuche, etc.)
access_handler = logging.FileHandler(access_log_path, encoding='utf-8')
access_handler.setLevel(logging.INFO)
access_formatter = logging.Formatter('%(asctime)s - ACCESS - %(levelname)s - %(message)s')
access_handler.setFormatter(access_formatter)

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# Root Logger Konfiguration
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers.clear()
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Separater Logger für Access-Events
access_logger = logging.getLogger("access")
access_logger.setLevel(logging.INFO)
access_logger.addHandler(access_handler)
access_logger.addHandler(console_handler)  # Auch in Console ausgeben

logger = logging.getLogger(__name__)
logger.info(f"🚀 Backend-Server wird gestartet - Logging initialisiert")
logger.info(f"📁 Backend-Logs: {log_path}")
logger.info(f"📁 Access-Logs: {access_log_path}")

class WorldCreationResponse(BaseModel):
    message: str
    world_id: int
    player_id: int
    initial_story: str
    final_world_name: Optional[str] = None

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_active_user(token: str = Depends(oauth2_scheme)):
    """
    Abhängigkeit, die den Benutzer aus dem JWT Token holt und prüft, ob er aktiv ist.
    """
    # Versuche JWT Token zu dekodieren
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Ungültige Authentifizierungsdaten",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extrahiere Benutzername aus Token
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=401,
            detail="Token enthält keinen gültigen Benutzernamen",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Lade Benutzer aus Datenbank
    user = db_manager.get_user_by_username(username)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Benutzer nicht gefunden",
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
    version="1.4.0"
)

# Request Logging Middleware - MUSS vor CORS stehen
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Sammle Request-Details
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    method = request.method
    url = str(request.url)
    
    # Log eingehende Anfrage in access.log
    access_logger.info(f"🌐 {method} {url} | IP: {client_ip} | UA: {user_agent[:100]}")
    
    # Spezielle Behandlung für kritische Endpunkte
    if "/token" in url:
        access_logger.info(f"🔐 Login-Versuch von IP: {client_ip} | User-Agent: {user_agent}")
        
        # Log Request Headers für CORS-Debugging
        origin = request.headers.get("origin", "None")
        referer = request.headers.get("referer", "None")
        content_type = request.headers.get("content-type", "None")
        access_logger.info(f"🔍 Headers: Origin={origin} | Referer={referer} | Content-Type={content_type}")
    
    # Verarbeite die Anfrage
    response = await call_next(request)
    
    # Berechne Antwortzeit
    process_time = time.time() - start_time
    
    # Log Response-Details
    access_logger.info(f"📤 Response: {response.status_code} | Zeit: {process_time:.3f}s | IP: {client_ip}")
    
    return response

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    import secrets
    
    response = await call_next(request)
    
    # Generiere einen neuen Nonce für jede Anfrage
    nonce = secrets.token_urlsafe(16)
    
    # Security Headers für HTTPS-Umgebung
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    # CSP mit dynamischem Nonce - Erlaube API-Zugriff über Reverse Proxy
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' https://cdn.tailwindcss.com https://unpkg.com; "
        f"style-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com; "
        f"font-src 'self' https://fonts.gstatic.com; "
        f"connect-src 'self' https://last-strawberry.com https://last-strawberry.com/api; "
        f"img-src 'self' data: https:; "
        f"object-src 'none'; "
        f"base-uri 'self'"
    )
    
    # Nonce für Frontend verfügbar machen
    response.headers["X-CSP-Nonce"] = nonce
    
    return response

# CORS-Konfiguration - Umgebungsbasierte Origins
import os

# Bestimme erlaubte Origins basierend auf Umgebung
def get_allowed_origins():
    # Produktionsumgebung
    production_origins = [
        "https://last-strawberry.com",
        "https://www.last-strawberry.com",
        "https://last-strawberry.com:443",
        "http://last-strawberry.com",
        "http://www.last-strawberry.com",
        "http://last-strawberry.com:8001",
        "https://last-strawberry.com:8001",
    ]
    
    # Entwicklungsumgebung
    development_origins = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8001",  
        "http://localhost:5000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:8001",
        "http://127.0.0.1:5000",
        "http://127.0.0.1",
        "http://localhost",
    ]
    
    # Prüfe ob Produktionsumgebung (anhand von Pfaden oder Environment Variables)
    is_production = (
        os.path.exists("/var/www/vhosts/last-strawberry.com/") or 
        os.environ.get("ENVIRONMENT") == "production" or
        os.environ.get("DEPLOY_ENV") == "production"
    )
    
    if is_production:
        logger.info("🌐 Produktionsumgebung erkannt - Verwende spezifische CORS Origins")
        # Auch in Produktion Port 8001 für Admin-Panel erlauben
        return production_origins + [
            "http://last-strawberry.com:8001",
            "https://last-strawberry.com:8001"
        ]
    else:
        logger.info("🛠️ Entwicklungsumgebung erkannt - Verwende erweiterte CORS Origins")
        return production_origins + development_origins  # Auch Produktion für Testing

allowed_origins = get_allowed_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Accept-Language", 
        "Content-Language",
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "X-CSRFToken",
    ],
    expose_headers=["X-Total-Count", "X-Page-Count"],
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Log CORS configuration
logger.info(f"🌍 CORS-Konfiguration: Origins={len(allowed_origins)} erlaubte Domains, Credentials=True")
logger.info(f"📋 Erlaubte Origins: {', '.join(allowed_origins[:3])}{'...' if len(allowed_origins) > 3 else ''}")

# --- Globale Instanzen ---
# Diese werden beim Start der Anwendung initialisiert
game_manager_instance: Optional[GameManagerOnline] = None
db_manager = DatabaseManager()

# --- KI-Kommunikation ---
async def get_google_auth_token():
    """Holt ein gültiges ID-Token für die Anfrage an den Cloud Run Dienst."""
    try:
        auth_req = requests.Request()
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
        logger.warning("Timeout bei der Anfrage an den KI-Dienst.")
        return "[Fehler: Die KI hat zu lange für eine Antwort gebraucht.]"
    except httpx.RequestError as e:
        logger.error(f"Request-Fehler beim KI-Dienst: {e}")
        return f"[Fehler: Der KI-Dienst unter {AI_SERVICE_URL} ist nicht erreichbar.]"
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP-Fehler vom KI-Dienst: {e.response.status_code} - {e.response.text}")
        return f"[Fehler: Der KI-Dienst hat einen Fehler gemeldet: {e.response.status_code}]"
    except Exception as e:
        logger.error(f"Unerwarteter Fehler bei der KI-Kommunikation: {e}", exc_info=True)
        return "[Ein unerwarteter interner Fehler ist bei der KI-Kommunikation aufgetreten.]"

@app.on_event("startup")
def startup_event():
    """Initialisiert den GameManager beim Start des Servers."""
    global game_manager_instance, db_manager
    db_manager.setup_database()    
    game_manager_instance = GameManagerOnline(ai_caller=call_ai_service)
    logger.info("Backend-Server gestartet, DB-Schema geprüft und GameManagerOnline initialisiert.")

# --- Login-System ---
# oauth2_scheme wurde bereits oben definiert - Duplikat entfernt

def get_current_admin_user(current_user: dict = Depends(get_current_active_user)):
    if "admin" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Keine Berechtigung für diese Aktion")
    return current_user

@app.get("/debug/test-logging")
async def test_logging(request: Request):
    """Test-Endpunkt für Logging-Funktionalität."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    
    logger.info(f"🧪 Debug-Test aufgerufen von IP: {client_ip} | UA: {user_agent}")
    logger.warning(f"⚠️ Test-Warning-Message")
    logger.error(f"❌ Test-Error-Message")
    
    return {
        "message": "Logging-Test erfolgreich",
        "ip": client_ip,
        "user_agent": user_agent,
        "timestamp": datetime.now().isoformat(),
        "log_file": str(project_root / "backend_server" / "backend.log")
    }

@app.get("/token", tags=["Auth"])
async def token_info():
    """Gibt Informationen über den Token-Endpunkt zurück (GET-Version für Tests)."""
    return {
        "message": "Token-Endpunkt ist erreichbar",
        "method": "POST",
        "description": "Verwende POST mit username/password für Anmeldung",
        "format": "application/x-www-form-urlencoded",
        "fields": ["username", "password"],
        "timestamp": datetime.now().isoformat()
    }

@app.post("/token", tags=["Auth"])
async def login(form_data: OAuth2PasswordRequestForm = Depends(), request: Request = None):
    """Überprüft Benutzerdaten gegen die DB und gibt einen Token zurück."""
    client_ip = request.client.host if request and request.client else "unknown"
    username = form_data.username
    
    access_logger.info(f"🔑 Login-Versuch für Benutzer '{username}' von IP: {client_ip}")
    
    try:
        user = db_manager.get_user_by_username(username)
        
        if not user:
            access_logger.warning(f"❌ Login fehlgeschlagen: Benutzer '{username}' nicht gefunden | IP: {client_ip}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
        
        if not verify_password(form_data.password, user["hashed_password"]):
            access_logger.warning(f"❌ Login fehlgeschlagen: Falsches Passwort für '{username}' | IP: {client_ip}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
        
        if not user.get('is_active', False):
            access_logger.warning(f"❌ Login fehlgeschlagen: Benutzer '{username}' ist deaktiviert | IP: {client_ip}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
        
        # Erstelle JWT Token mit Benutzerdaten
        token_data = {
            "sub": user["username"],  # Subject (Benutzername)
            "user_id": user["user_id"],
            "roles": user.get("roles", []),
            "is_active": user.get("is_active", False)
        }
        
        access_token = create_access_token(data=token_data)
        
        access_logger.info(f"✅ Login erfolgreich für Benutzer '{username}' | IP: {client_ip} | Rollen: {user.get('roles', [])} | Token erstellt")
        return {
            "access_token": access_token, 
            "token_type": "bearer", 
            "roles": user.get("roles", []),
            "expires_in": 24 * 60 * 60  # 24 Stunden in Sekunden
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        access_logger.error(f"💥 Unerwarteter Fehler beim Login für '{username}' | IP: {client_ip} | Error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

# --- Admin-Bereich: Benutzerverwaltung ---
class UserCreate(BaseModel):
    username: str
    password: str
    roles: List[str] = ["gamemaster"]

class UserUpdateRequest(BaseModel):
    password: Optional[str] = None
    roles: Optional[List[str]] = None

@app.get("/admin/users", response_model=List[Dict[str, Any]], tags=["Admin - Users"], dependencies=[Depends(get_current_admin_user)])
def list_users():
    """Listet alle Benutzer auf (nur für Admins)."""
    return db_manager.get_all_users()

@app.post("/admin/users", dependencies=[Depends(get_current_admin_user)])
def create_new_user(user_data: UserCreate):
    user_id = db_manager.create_user(
        username=user_data.username,
        hashed_password=get_password_hash(user_data.password),
        roles=user_data.roles
    )
    if not user_id:
        raise HTTPException(status_code=400, detail="Benutzer konnte nicht erstellt werden oder existiert bereits.")
    return {"message": "Benutzer erfolgreich erstellt", "user_id": user_id}

@app.put("/admin/users/{user_id}", dependencies=[Depends(get_current_admin_user)])
def update_user_details(user_id: int, request: UserUpdateRequest):
    if request.password:
        db_manager.update_user_password(user_id, get_password_hash(request.password))
    if request.roles is not None and user_id != 1: # Schütze Rollen von User 1
        db_manager.update_user_roles(user_id, request.roles)
    return {"message": f"Benutzer {user_id} aktualisiert"}

@app.put("/admin/users/{user_id}/status", tags=["Admin - Users"], dependencies=[Depends(get_current_admin_user)])
async def change_user_status(user_id: int, is_active: bool):
    """Aktiviert oder deaktiviert einen Benutzer (nur für Admins)."""
    if user_id == 1:
        raise HTTPException(status_code=403, detail="Cannot deactivate UserID=1.")
    success = db_manager.update_user_status(user_id, is_active)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": f"User status set to {'active' if is_active else 'inactive'}"}

# --- User Profile Management ---
class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

@app.put("/profile/password", tags=["Profile"])
async def change_own_password(request: PasswordChangeRequest, current_user: dict = Depends(get_current_active_user)):
    """Ermöglicht es Benutzern, ihr eigenes Passwort zu ändern."""
    # Aktuelles Passwort verifizieren
    if not verify_password(request.current_password, current_user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Aktuelles Passwort ist falsch")
    
    # Neues Passwort validieren
    if len(request.new_password) < 6:
        raise HTTPException(status_code=400, detail="Neues Passwort muss mindestens 6 Zeichen lang sein")
    
    # Passwort aktualisieren
    success = db_manager.update_user_password(current_user["user_id"], get_password_hash(request.new_password))
    if not success:
        raise HTTPException(status_code=500, detail="Passwort konnte nicht aktualisiert werden")
    
    return {"message": "Passwort erfolgreich geändert"}

@app.get("/profile", tags=["Profile"])
async def get_profile(current_user: dict = Depends(get_current_active_user)):
    """Gibt die Profil-Informationen des aktuellen Benutzers zurück."""
    return {
        "user_id": current_user["user_id"],
        "username": current_user["username"],
        "roles": current_user.get("roles", []),
        "created_at": current_user.get("created_at", ""),
        "is_active": current_user.get("is_active", True)
    }

# --- Story Export & Management ---
from fastapi.responses import Response
import json
from datetime import datetime

@app.get("/worlds/{world_id}/story/export", tags=["Story"])
async def export_story(world_id: int, format: str = "txt", current_user: dict = Depends(get_current_active_user)):
    """Exportiert die komplette Story einer Welt in verschiedenen Formaten."""
    try:
        # Hole alle Story-Events für diese Welt
        story_events = db_manager.get_story_events_for_world(world_id)
        
        if not story_events:
            raise HTTPException(status_code=404, detail="Keine Story-Events für diese Welt gefunden")
        
        # Hole Welt-Informationen
        world_info = db_manager.get_world_info(world_id)
        player_info = db_manager.get_player_info_for_world(world_id)
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{world_info['world_name']}_{timestamp}"
        
        if format.lower() == "json":
            # JSON Export mit vollständigen Metadaten
            export_data = {
                "metadata": {
                    "world_name": world_info['world_name'],
                    "character_name": player_info['character_name'] if player_info else "Unknown",
                    "export_date": datetime.now().isoformat(),
                    "total_events": len(story_events)
                },
                "world_lore": world_info.get('lore', ''),
                "character_backstory": player_info.get('backstory', '') if player_info else '',
                "story_events": story_events
            }
            
            content = json.dumps(export_data, indent=2, ensure_ascii=False)
            media_type = "application/json"
            filename += ".json"
            
        elif format.lower() == "markdown":
            # Markdown Export für bessere Lesbarkeit
            content = f"# {world_info['world_name']} - Abenteuer-Log\n\n"
            content += f"**Charakter:** {player_info['character_name'] if player_info else 'Unknown'}\n"
            content += f"**Exportiert am:** {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            
            if world_info.get('lore'):
                content += f"## Welt-Lore\n{world_info['lore']}\n\n"
            
            if player_info and player_info.get('backstory'):
                content += f"## Charakter-Hintergrund\n{player_info['backstory']}\n\n"
            
            content += "## Abenteuer-Verlauf\n\n"
            
            for i, event in enumerate(story_events, 1):
                event_time = datetime.fromisoformat(event['timestamp']).strftime('%d.%m.%Y %H:%M')
                content += f"### {i}. {event_time}\n\n"
                
                if event['event_type'] == 'PLAYER_ACTION':
                    content += f"**Spieler-Aktion:** {event['content']}\n\n"
                elif event['event_type'] == 'STORY':
                    content += f"{event['content']}\n\n"
                elif event['event_type'] == 'LEVEL_UP':
                    content += f"🎉 **Level Up!** {event['content']}\n\n"
                
                content += "---\n\n"
            
            media_type = "text/markdown"
            filename += ".md"
            
        else:  # TXT format (default)
            # Einfacher Text Export
            content = f"{world_info['world_name']} - Abenteuer-Log\n"
            content += f"Charakter: {player_info['character_name'] if player_info else 'Unknown'}\n"
            content += f"Exportiert am: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            content += "=" * 50 + "\n\n"
            
            if world_info.get('lore'):
                content += f"WELT-LORE:\n{world_info['lore']}\n\n"
            
            if player_info and player_info.get('backstory'):
                content += f"CHARAKTER-HINTERGRUND:\n{player_info['backstory']}\n\n"
            
            content += "ABENTEUER-VERLAUF:\n\n"
            
            for i, event in enumerate(story_events, 1):
                event_time = datetime.fromisoformat(event['timestamp']).strftime('%d.%m.%Y %H:%M')
                content += f"{i}. [{event_time}]\n"
                
                if event['event_type'] == 'PLAYER_ACTION':
                    content += f"Spieler: {event['content']}\n"
                elif event['event_type'] == 'STORY':
                    content += f"Story: {event['content']}\n"
                elif event['event_type'] == 'LEVEL_UP':
                    content += f"Level Up: {event['content']}\n"
                
                content += "\n" + "-" * 40 + "\n\n"
            
            media_type = "text/plain"
            filename += ".txt"
        
        # Return file as download
        return Response(
            content=content.encode('utf-8'),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": f"{media_type}; charset=utf-8"
            }
        )
        
    except Exception as e:
        logger.error(f"Error exporting story for world {world_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Fehler beim Exportieren der Story: {str(e)}")

@app.get("/worlds/{world_id}/statistics", tags=["Story"])
async def get_world_statistics(world_id: int, current_user: dict = Depends(get_current_active_user)):
    """Gibt Statistiken für eine Welt zurück."""
    try:
        stats = db_manager.get_world_statistics(world_id)
        return stats
    except Exception as e:
        logger.error(f"Error getting statistics for world {world_id}: {e}")
        raise HTTPException(status_code=500, detail="Fehler beim Laden der Statistiken")

def run_script_in_background(allowed_key: str, world_id: int = None, world_name: str = None):
    """Führt ein zugelassenes Python-Skript im Hintergrund aus und validiert die Argumente."""
    if allowed_key not in ALLOWED_SCRIPTS:
        logger.error(f"Unzulässiger Skriptname: {allowed_key}")
        return False

    script_path = ALLOWED_SCRIPTS[allowed_key]
    if not script_path.exists():
        logger.error(f"Skript nicht gefunden: {script_path}")
        return False

    args = []
    if allowed_key == "train_narrative":
        if not isinstance(world_id, int) or world_id <= 0:
            logger.error(f"Versuch, Skript mit ungültiger world_id zu starten: {world_id}")
            return False
        if not world_name or not re.fullmatch(r"[A-Za-z0-9 _\-äöüÄÖÜß]+", world_name) or len(world_name) > 50:
            logger.error(f"Versuch, Skript mit ungültigem oder zu langem world_name zu starten: '{world_name}'")
            return False
        args = [str(world_id), world_name]
    
    try:
        command = [sys.executable, str(script_path)] + args
        logger.info(f"Führe Befehl aus: {command}")

        # Die `codeql` Direktive erklärt dem Tool, warum dies sicher ist.
        # 1. shell=False (Standard): Verhindert, dass die Shell den Befehl interpretiert.
        # 2. command ist eine Liste: Argumente werden direkt an den Prozess übergeben,
        #    ohne Shell-Expansion.
        # 3. Strikte Eingabevalidierung (siehe oben) verhindert schädliche Inhalte in `args`.
        # codeql[py/command-line-injection]
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True
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
    if world_id <= 0:
         raise HTTPException(status_code=400, detail="world_id muss eine positive Ganzzahl sein.")

    success = run_script_in_background("train_narrative", world_id, world_name)
    if not success:
        raise HTTPException(status_code=500, detail="Das Erzähl-Trainingsskript konnte nicht gestartet werden.")

    return {"message": f"Erzähl-Training für Welt '{world_name}' wurde im Hintergrund gestartet."}

@app.get("/get_last_event", tags=["Game"])
async def get_last_event(world_id: int, player_id: int, current_user: dict = Depends(get_current_active_user)):
    """
    Lädt das letzte Event für das DM-Korrekturwerkzeug.
    Gibt ai_output und extracted_commands_json zurück.
    """
    try:
        # Hole das letzte Event aus der Datenbank
        event = db_manager.get_last_event_for_world_player(world_id, player_id)
        if not event:
            raise HTTPException(status_code=404, detail="Kein Event für diese Welt/Spieler gefunden")
        
        # Stelle sicher, dass extracted_commands_json als String zurückgegeben wird
        if event.get('extracted_commands_json'):
            try:
                # Validiere JSON und konvertiere zurück zu String für Frontend
                json.loads(event['extracted_commands_json'])
            except (json.JSONDecodeError, TypeError):
                event['extracted_commands_json'] = '[]'
        else:
            event['extracted_commands_json'] = '[]'
        
        return {"event": event}
        
    except Exception as e:
        logger.error(f"Fehler beim Laden des letzten Events: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class EventCorrectionRequest(BaseModel):
    world_id: int
    player_id: int  
    ai_output: str
    extracted_commands_json: str

@app.post("/save_event_correction", tags=["Game"])
async def save_event_correction(request: EventCorrectionRequest, current_user: dict = Depends(get_current_active_user)):
    """
    Speichert Korrekturen des letzten Events für Trainingsdaten.
    """
    try:
        # Validiere JSON
        try:
            json.loads(request.extracted_commands_json)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Ungültiges JSON-Format in extracted_commands_json")
        
        # Hole das letzte Event
        event = db_manager.get_last_event_for_world_player(request.world_id, request.player_id)
        if not event:
            raise HTTPException(status_code=404, detail="Kein Event zum Korrigieren gefunden")
        
        # Speichere die Korrektur
        success = db_manager.update_event_correction(
            event_id=event['event_id'],
            corrected_ai_output=request.ai_output,
            corrected_commands_json=request.extracted_commands_json
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Korrektur konnte nicht gespeichert werden")
        
        return {"message": "Event-Korrektur erfolgreich gespeichert"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Speichern der Event-Korrektur: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class WorldCreateRequest(BaseModel):
    world_name: str
    lore: str
    char_name: str
    backstory: str
    attributes: Dict[str, int] 
    template_key: str = "system_fantasy"

@app.get("/worlds", tags=["Game"])
async def get_all_worlds(current_user: dict = Depends(get_current_active_user)):
    """Gibt eine Liste aller existierenden Welten und deren Spieler zurück."""
    worlds = db_manager.get_all_worlds_and_players()
    return {"worlds": worlds}

@app.post("/worlds/create", response_model=WorldCreationResponse, tags=["Game"])
async def create_new_world(request: WorldCreateRequest, current_user: dict = Depends(get_current_active_user)):
    logger.info(f"Anfrage zur Welterstellung für '{request.world_name}' von Benutzer {current_user['username']} erhalten.")
    try:
        initial_conditions = await game_manager_instance._generate_initial_conditions(
            world_lore=request.lore,
            char_backstory=request.backstory
        )
        if not initial_conditions:
            raise HTTPException(status_code=500, detail="KI konnte keine validen Startbedingungen erstellen.")

        new_ids = db_manager.create_world_and_player(
            world_name=request.world_name, lore=request.lore, template_key=request.template_key,
            user_id=current_user['user_id'], # Übergibt die ID des angemeldeten Benutzers
            char_name=request.char_name, backstory=request.backstory, char_attributes=request.attributes,
            initial_location_name=initial_conditions['location_name'],
            initial_location_desc=initial_conditions['location_description'],
            initial_state_dict=initial_conditions['initial_state']
        )
        
        # Verbesserte Fehlerbehandlung
        if not new_ids:
            raise HTTPException(status_code=500, detail="Fehler beim Speichern der neuen Welt in der Datenbank.")
        
        # Prüfe auf spezifische Fehler
        if isinstance(new_ids, dict) and "error" in new_ids:
            if new_ids["error"] == "world_name_exists":
                raise HTTPException(status_code=400, detail=f"Ein Welt mit dem Namen '{request.world_name}' existiert bereits. Bitte wählen Sie einen anderen Namen.")
            elif new_ids["error"] == "integrity_error":
                raise HTTPException(status_code=400, detail="Datenintegritätsfehler beim Erstellen der Welt.")
            elif new_ids["error"] == "database_error":
                raise HTTPException(status_code=500, detail="Datenbankfehler beim Erstellen der Welt.")
            else:
                raise HTTPException(status_code=500, detail="Unbekannter Fehler beim Erstellen der Welt.")

        game_manager_instance._load_game_state(new_ids['world_id'], new_ids['player_id'])
        game_manager_instance.is_new_game = True
        initial_story_response = await game_manager_instance.get_initial_story_prompt()

        # Extrahiere den eigentlichen Story-Text aus der AI-Antwort
        if isinstance(initial_story_response, dict) and "response" in initial_story_response:
            initial_story_text = initial_story_response["response"]
        else:
            initial_story_text = str(initial_story_response)

        # Verwende den finalen Weltnamen (falls geändert)
        final_world_name = new_ids.get('final_world_name', request.world_name)
        
        return {
            "message": f"Welt '{final_world_name}' erfolgreich erstellt", 
            "world_id": new_ids['world_id'],
            "player_id": new_ids['player_id'], 
            "initial_story": initial_story_text,
            "final_world_name": final_world_name
        }
    except Exception as e:
        logger.error(f"Fehler bei der Welterstellung: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ein interner Fehler ist bei der Welterstellung aufgetreten.")

class CommandRequest(BaseModel):
    command: str
    world_id: int
    player_id: int

@app.post("/command", tags=["Game"])
async def process_command(request: CommandRequest, current_user: dict = Depends(get_current_active_user)):
    """Nimmt einen Spieler-Befehl entgegen und gibt die Antwort des Spiels zurück."""
    if not game_manager_instance:
        raise HTTPException(status_code=503, detail="GameManager ist nicht initialisiert.")
        
    # player_id ist eigentlich char_id aus der Datenbank
    char_id = request.player_id
    if not db_manager.is_user_authorized_for_player(current_user['user_id'], char_id):
        raise HTTPException(status_code=403, detail="Permission denied to act for this player.")

    game_manager_instance._load_game_state(request.world_id, char_id)
    response = await game_manager_instance.process_player_command(request.command)
    
    return response

@app.get("/load_game_summary", tags=["Game"])
async def load_game_summary(world_id: int, player_id: int, current_user: dict = Depends(get_current_active_user)):
    """Gibt die Start-Zusammenfassung für ein spezifisches Spiel zurück."""
    if not game_manager_instance:
        raise HTTPException(status_code=503, detail="GameManager ist nicht initialisiert.")

    # player_id ist eigentlich char_id aus der Datenbank
    char_id = player_id
    if not db_manager.is_user_authorized_for_player(current_user['user_id'], char_id):
        raise HTTPException(status_code=403, detail="Permission denied to access this game summary.")

    game_manager_instance._load_game_state(world_id, char_id)
    game_manager_instance.is_new_game = False
    
    summary = await game_manager_instance.get_load_game_summary()
    return {"response": summary}

@app.get("/")
async def root():
    """Root endpoint für die API."""
    return {
        "message": "Last-Strawberry Backend Server",
        "version": "1.4.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health")
async def root_health_check():
    """Health check endpoint - testet Backend-Funktionalität ohne AI-Service Dependencies."""
    ai_status = {"status": "not_checked", "message": "AI service check skipped for stability"}
    
    # Teste nur die Datenbankverbindung, nicht den AI-Service
    try:
        # Einfacher DB-Test
        test_user = db_manager.get_user_by_username("test_connection")
        db_status = "ok"
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        db_status = "error"
    
    # Optional: AI-Service testen, aber Fehler ignorieren
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{AI_SERVICE_URL}/health")
            if response.status_code == 200:
                ai_status = {"status": "ok", "response": response.json()}
            else:
                ai_status = {"status": "unreachable", "code": response.status_code}
    except Exception as e:
        logger.warning(f"AI service health check failed: {e}")
        ai_status = {"status": "unreachable", "error": "An error occurred while checking AI service health."}
    
    return {
        "status": "ok",
        "service": "Backend Server", 
        "database": db_status,
        "ai_service_status": ai_status,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/ping")
async def ping():
    """
    Ping-Endpunkt für Google Cloud Run Kaltstart-Vermeidung.
    Kann verwendet werden, um den Service warm zu halten.
    """
    return {
        "status": "pong", 
        "service": "Backend Server",
        "timestamp": datetime.now().isoformat(),
        "version": "1.4.0"
    }

class AttributeUpdateRequest(BaseModel):
    player_id: int
    new_attributes: Dict[str, int]

@app.post("/character/update_attributes", tags=["Game"])
async def update_attributes(request: AttributeUpdateRequest, current_user: dict = Depends(get_current_active_user)):
    """Speichert die vom Spieler nach einem Level-Up verteilten Attributspunkte."""
    if not db_manager.is_user_authorized_for_player(current_user['user_id'], request.player_id):
        raise HTTPException(status_code=403, detail="Permission denied to update attributes for this player.")

    success = db_manager.update_character_attributes(request.player_id, request.new_attributes)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update attributes in database.")
    
    return {"message": "Attributes updated successfully."}

# --- Server-Start ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,  # Reload deaktiviert für stabileren Test
        log_level="info"
    )
