# tools/train_model.py
# -*- coding: utf-8 -*-

"""
A command-line tool to start the fine-tuning process for a SPECIFIC WORLD.
After successful training, it automatically cleans up old adapters and
forces a clean exit to release all system resources.
"""

import sys
import logging
from pathlib import Path
import datetime
import argparse
import os
import shutil
# NEU: Imports für den finalen Cleanup
import gc
import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from class_folder.core.database_manager import DatabaseManager
    from class_folder.core.hf_fine_tuner import HFFineTuner
except ImportError as e:
    logging.basicConfig()
    logging.critical(f"Could not import a required class. Error: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def cleanup_old_adapters(world_name: str):
    # This function remains unchanged
    adapter_base_dir = Path("./trained_adapters")
    if not adapter_base_dir.exists():
        return

    world_name_safe = world_name.replace(" ", "_")
    
    world_adapters = [
        d for d in adapter_base_dir.iterdir() 
        if d.is_dir() and d.name.startswith(world_name_safe)
    ]
    
    if len(world_adapters) <= 1:
        print("Keine alten Adapter zum Löschen gefunden.")
        return

    world_adapters.sort(key=os.path.getctime, reverse=True)
    adapters_to_delete = world_adapters[1:]
    
    print(f"Gefunden: {len(adapters_to_delete)} alte Adapter zum Löschen.")
    
    for adapter_path in adapters_to_delete:
        try:
            shutil.rmtree(adapter_path)
            print(f" - Gelöscht: {adapter_path.name}")
        except OSError as e:
            print(f"Fehler beim Löschen von {adapter_path.name}: {e}")

def run_training(world_id: int):
    """
    Main function to start the training process for a specific world.
    """
    fine_tuner = None # Vor-initialisieren für den finally-Block
    try:
        print("=============================================")
        print(f"=== Last-Strawberry AI Fine-Tuning für Welt #{world_id} ===")
        print("=============================================")

        db_manager = DatabaseManager()
        
        world_info = db_manager.get_world_info(world_id)
        if not world_info:
            print(f"\nFehler: Welt mit ID {world_id} nicht in der Datenbank gefunden.")
            return

        world_name = world_info.get('name', f'world_{world_id}').replace(" ", "_")
        
        events_for_training = db_manager.get_events_for_review(label='gut (Training)', world_id=world_id)
        if not events_for_training:
            print(f"\nFehler: Keine als 'gut (Training)' markierten Ereignisse für Welt '{world_name}' (ID: {world_id}) gefunden.")
            return

        output_dir = f"./trained_adapters/{world_name}_adapter_{datetime.datetime.now().strftime('%Y%m%d-%H%M')}"
        
        training_config = {
            "epochs": 1,
            "batch_size": 1,
            "gradient_accumulation": 8,
            "learning_rate": 2e-4,
            "max_seq_length": 1024,
            "output_dir": output_dir
        }

        print(f"\n{len(events_for_training)} hochwertige Ereignisse für das Training von Welt '{world_name}' gefunden.")
        print(f"Der neue LoRA-Adapter wird in folgendem Verzeichnis gespeichert:\n{Path(output_dir).resolve()}")
        
        choice = input("\nMöchten Sie das Training mit diesen Einstellungen starten? (j/n): ").lower()
        if choice != 'j':
            print("Training abgebrochen.")
            return

        fine_tuner = HFFineTuner(db_manager=db_manager, training_config=training_config, world_id=world_id)
        success = fine_tuner.run_fine_tuning()
        
        if success:
            print(f"\nTraining für Welt '{world_name}' erfolgreich abgeschlossen!")
            print(f"Der neue Adapter wurde unter '{output_dir}' gespeichert.")
            print("\nSuche nach alten Adaptern für diese Welt, um sie zu bereinigen...")
            cleanup_old_adapters(world_name)
        else:
            print("\nDas Training ist fehlgeschlagen.")

    except Exception as e:
        logger.error(f"Ein unerwarteter Fehler ist im Hauptskript aufgetreten: {e}", exc_info=True)
    
    finally:
        # NEUE LOGIK: Finaler, aggressiver Cleanup, egal was passiert.
        print("\nFühre finalen Speicher-Cleanup durch...")
        if fine_tuner:
            del fine_tuner.model
            del fine_tuner.tokenizer
            del fine_tuner
        
        gc.collect()
        torch.cuda.empty_cache()
        print("Cleanup abgeschlossen. Skript wird beendet.")
        sys.exit(0) # Beendet den Prozess sauber und gibt alle Ressourcen frei.

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fine-tune the AI model for a specific world and clean up old adapters.")
    parser.add_argument("world_id", type=int, help="The ID of the world to train on.")
    args = parser.parse_args()
    
    run_training(args.world_id)
