# ai_service/main.py
# -*- coding: utf-8 -*-

"""
Dies ist der Haupt-Endpunkt für den KI-Dienst, der als serverloser Container
in der Google Cloud laufen soll. Er verwendet FastAPI, um einen Webserver bereitzustellen.
"""

import logging
import sys
import os

from pathlib import Path
from pydantic import BaseModel

# Füge das Projektverzeichnis zum Python-Pfad hinzu, damit die Imports funktionieren
# Wir gehen davon aus, dass sich dieses Skript in 'ai_service/' befindet und die Klassen in 'class_folder/'
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from fastapi import FastAPI, HTTPException
# Importiere den bestehenden InferenceService
from class_folder.core.inference_service import InferenceService

# --- Logging-Konfiguration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- FastAPI App und KI-Dienst initialisieren ---
app = FastAPI(
    title="Last-Strawberry AI Service",
    description="Ein Dienst, der Inferenz für das Text-Abenteuer durchführt.",
    version="1.0.0"
)

# Das KI-Modell wird nur einmal beim Start des Containers geladen.
# Cloud Run hält den Container "warm", solange Anfragen kommen.
# Wenn keine Anfragen mehr kommen, wird der Container heruntergefahren (Skalierung auf Null).

inference_service: InferenceService | None = None
@app.on_event("startup")
def load_model():
    """Wird beim Start der FastAPI-Anwendung ausgeführt, um das Modell zu laden."""
    global inference_service
    try:
        logger.info("Versuche, den InferenceService beim Start zu laden...")
        inference_service = InferenceService()
        if not inference_service.base_model_loaded:
             # Wenn das Modell nicht geladen wurde, wird ein Fehler geloggt.
             raise RuntimeError(f"Modell konnte nicht geladen werden: {inference_service.load_status}")
        logger.info("InferenceService erfolgreich beim Start geladen.")
    except Exception as e:
        logger.critical(f"Kritischer Fehler beim Laden des InferenceService: {e}", exc_info=True)
        # Setze den Dienst auf None, damit Health-Checks fehlschlagen.
        inference_service = None

class InferenceRequest(BaseModel):
    """
    Definiert die Struktur für eine Anfrage an den KI-Dienst.
    """
    prompt: str
    world_name: str  # Um den richtigen Adapter zu laden
    adapter_type: str = 'NARRATIVE' # 'NARRATIVE' oder 'ANALYSIS'

class InferenceResponse(BaseModel):
    """
    Definiert die Struktur für die Antwort des KI-Dienstes.
    """
    generated_text: str
    model_load_status: str

# --- API-Endpunkt ---

@app.post("/generate", response_model=InferenceResponse)
async def generate_text(request: InferenceRequest):
    """
    Nimmt einen Prompt entgegen, führt die Inferenz durch und gibt den generierten Text zurück.
    """
    if not inference_service or not inference_service.base_model_loaded:
        raise HTTPException(status_code=503, detail="KI-Modell ist nicht verfügbar oder wird noch geladen.")

    try:
        logger.info(f"🎯 Anfrage für Welt '{request.world_name}' mit Adapter-Typ '{request.adapter_type}' erhalten.")
        logger.info(f"📝 Prompt-Preview (erste 200 Zeichen): {request.prompt[:200]}...")
        
        # Lade den passenden Adapter für die Anfrage
        inference_service.switch_to_adapter(request.adapter_type, request.world_name)
        
        # Generiere die Antwort
        generated_text = inference_service.generate_story_response(request.prompt)
        
        logger.info(f"✅ Antwort generiert ({len(generated_text)} Zeichen) für Adapter '{request.adapter_type}'")
        
        return InferenceResponse(
            generated_text=generated_text,
            model_load_status=inference_service.load_status
        )
    except Exception as e:
        logger.error(f"❌ Fehler während der Inferenz: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ein interner Fehler ist aufgetreten: {e}")

@app.get("/health")
async def health_check():
    """
    Ein einfacher Endpunkt, um zu prüfen, ob der Dienst läuft und das Modell geladen ist.
    """
    if inference_service and inference_service.base_model_loaded:
        return {"status": "ok", "message": "KI-Modell ist geladen und bereit."}
    else:
        status_message = "KI-Modell konnte nicht geladen werden."
        if inference_service:
            status_message = inference_service.load_status
        return {"status": "unavailable", "message": status_message}

# Um den Server lokal zu testen, führen Sie im Terminal aus:
# uvicorn ai_service.main:app --reload
