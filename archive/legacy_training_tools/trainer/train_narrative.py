# train_narrative.py
# -*- coding: utf-8 -*-

"""
Dieses Skript startet den Fine-Tuning-Prozess für das Erzähl-Modell (World-LLM)
einer spezifischen Welt. Es wird vom Backend-Server aufgerufen.
"""

import logging
import sys
import shutil
import datetime
from pathlib import Path

# Füge das Projektverzeichnis zum Python-Pfad hinzu
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from class_folder.core.hf_fine_tuner import HFFineTuner
from class_folder.core.database_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
ADAPTERS_BASE_DIR = project_root / "trained_adapters"
ADAPTERS_BASE_DIR.mkdir(exist_ok=True)

def main():
    """Hauptfunktion zum Starten des Trainings und der anschließenden Verwaltung."""
    
    # Das Skript erwartet die world_id und den world_name als Kommandozeilen-Argumente
    if len(sys.argv) < 3:
        logger.error("Fehler: Es wurden world_id und world_name benötigt.")
        logger.error("Aufruf: python train_narrative.py <world_id> <world_name>")
        sys.exit(1)

    try:
        world_id = int(sys.argv[1])
        world_name = sys.argv[2]
        # Bereinige den Welt-Namen für die Verwendung in Dateipfaden
        safe_world_name = "".join(c if c.isalnum() else "_" for c in world_name)
    except ValueError:
        logger.error(f"Fehler: Ungültige world_id '{sys.argv[1]}'. Muss eine Zahl sein.")
        sys.exit(1)

    logger.info(f"Starte NARRATIVE-Training für Welt '{world_name}' (ID: {world_id})")

    # Schritt 1: Training durchführen
    db_manager = DatabaseManager()
    
    # Temporäres Ausgabeverzeichnis für das Training
    temp_output_dir = project_root / f"lora_narrative_output_temp_{safe_world_name}"
    
    config = {
        "max_seq_length": 1024,
        "output_dir": str(temp_output_dir)
    } 
    fine_tuner = HFFineTuner(
        db_manager=db_manager,
        training_config=config,
        world_id=world_id, 
        task_type='NARRATIVE'
    )

    # Starte das Training
    success = fine_tuner.run_fine_tuning()
    
    if success:
        logger.info(f"NARRATIVE-Training für world_id {world_id} erfolgreich abgeschlossen.")
    else:
        logger.error(f"NARRATIVE-Training für world_id {world_id} ist fehlgeschlagen.")

    db_manager.close_connection()

    if not success:
        logger.error(f"Fine-Tuning für Welt '{world_name}' ist fehlgeschlagen.")
        if temp_output_dir.exists():
            shutil.rmtree(temp_output_dir)
        return

    # Schritt 2: Aufräumen und Versionieren
    logger.info("Training erfolgreich. Versioniere den neuen Erzähl-Adapter...")
    
    world_adapter_dir = ADAPTERS_BASE_DIR / safe_world_name
    world_adapter_dir.mkdir(exist_ok=True)

    # Lösche alle alten Adapter für diese spezifische Welt
    for old_adapter in world_adapter_dir.glob("*"):
        if old_adapter.is_dir():
            logger.info(f"Lösche alten Adapter für '{world_name}': {old_adapter.name}")
            shutil.rmtree(old_adapter)

    # Erstelle einen neuen, eindeutigen Namen für den Adapter
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    new_adapter_name = f"narrative_adapter_v{timestamp}"
    final_adapter_path = world_adapter_dir / new_adapter_name
    
    # Verschiebe und benenne den neuen Adapter um
    try:
        shutil.move(str(temp_output_dir), str(final_adapter_path))
        logger.info(f"Neuer Adapter für '{world_name}' erfolgreich nach '{final_adapter_path}' verschoben.")
    except Exception as e:
        logger.error(f"Fehler beim Verschieben des neuen Adapters: {e}")

    print("-" * 50)
    logger.info(f"Erzähl-Modell-Training für Welt '{world_name}' abgeschlossen.")
    print("-" * 50)


if __name__ == "__main__":
    main()

