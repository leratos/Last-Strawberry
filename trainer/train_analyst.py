# train_analyst.py
"""
Dieses Skript führt den gesamten Prozess des Analyse-Modell-Trainings aus:
1. Es generiert die neuesten Trainingsdaten aus den DM-Korrekturen.
2. Es startet das Fine-Tuning.
3. Es räumt nach erfolgreichem Training auf, versioniert den neuen Adapter
   und löscht den alten.
"""
import logging
import sys
import shutil
import datetime
from pathlib import Path

# Füge das Projektverzeichnis zum Python-Pfad hinzu
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))
try:
    from server_tools.generate_analysis_data_from_db import main as generate_data
    CAN_GENERATE_DATA = True
except ImportError:
    CAN_GENERATE_DATA = False
from class_folder.core.hf_fine_tuner import HFFineTuner
from class_folder.core.database_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Hauptfunktion zum Starten des Trainings und der anschließenden Verwaltung."""
    
    # Schritt 1: Trainingsdaten aktualisieren
    if CAN_GENERATE_DATA:
        print("-" * 50)
        logger.info("Aktualisiere Trainingsdaten aus DM-Korrekturen...")
        generate_data()
        logger.info("Aktualisierung der DM-Daten abgeschlossen.")
        print("-" * 50)
    else:
        logger.warning("Konnte das Skript zur Datengenerierung nicht importieren. Überspringe diesen Schritt.")
        
    # Schritt 2: Training durchführen
    db_manager = DatabaseManager()
    
    # Das temporäre Ausgabeverzeichnis für das Training
    temp_output_dir = project_root / "lora_adapter_output_temp"
    
    config = {
        "max_seq_length": 1024,
        "output_dir": str(temp_output_dir)
    } 
    fine_tuner = HFFineTuner(
        db_manager=db_manager,
        training_config=config,
        world_id=0, 
        task_type='ANALYSIS'
    )

    success = fine_tuner.run_fine_tuning()
    db_manager.close_connection()

    if not success:
        logger.error("Fine-Tuning ist fehlgeschlagen. Es werden keine Dateien verschoben oder gelöscht.")
        if temp_output_dir.exists():
            shutil.rmtree(temp_output_dir)
        return

    # Schritt 3: Aufräumen und Versionieren nach erfolgreichem Training
    logger.info("Training erfolgreich. Versioniere den neuen Adapter...")
    
    # Finde alle alten Analyse-Adapter im Zielverzeichnis 'adapter'
    adapter_dir = project_root / "adapter"
    adapter_dir.mkdir(exist_ok=True) # Stelle sicher, dass der Ordner existiert

    for old_adapter in adapter_dir.glob("analysis_adapter_v*"):
        if old_adapter.is_dir():
            logger.info(f"Versuche, alten Adapter zu löschen: {old_adapter.name}")
            try:
                # NEU: Robuster Löschversuch mit Fehlerbehandlung
                shutil.rmtree(old_adapter)
                logger.info(f"Alter Adapter '{old_adapter.name}' erfolgreich gelöscht.")
            except (OSError, PermissionError) as e:
                logger.warning(f"Konnte alten Adapter '{old_adapter.name}' nicht löschen: {e}")
                logger.warning("BITTE LÖSCHE DEN ORDNER MANUELL, um Konflikte zu vermeiden.")

    # Erstelle einen neuen, eindeutigen Namen für den Adapter
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    new_adapter_name = f"analysis_adapter_v{timestamp}"
    final_adapter_path = adapter_dir / new_adapter_name
    
    # Verschiebe und benenne den neuen Adapter um
    try:
        shutil.move(str(temp_output_dir), str(final_adapter_path))
        logger.info(f"Neuer Adapter erfolgreich nach '{final_adapter_path}' verschoben.")
    except Exception as e:
        logger.error(f"FATALER FEHLER: Konnte den neuen Adapter von '{temp_output_dir}' nicht verschieben: {e}")
        logger.error("Der neue Adapter befindet sich noch im temporären Ordner. Bitte manuell verschieben!")

    print("-" * 50)
    logger.info("Analyse-Modell-Training und Verwaltung abgeschlossen.")
    print("-" * 50)


if __name__ == "__main__":
    main()
