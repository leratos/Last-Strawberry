# cronjob/tower_data_processor.py
# -*- coding: utf-8 -*-
"""
Handles fetching and preparing world-specific data from the central server.
Part 1 of the EVA-Process for the Last-Strawberry Tower.
This script is responsible for the 'E' (Eingabe/Input) phase.
"""
import requests
from pathlib import Path
import logging
import json
import sys
import shutil
from typing import Optional, List, Dict, Any

# Add project root to path to allow importing project classes
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from class_folder.core.database_manager import DatabaseManager
except ImportError as e:
    logging.critical(f"Could not import DatabaseManager. Error: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Configuration ---
TOWER_CONFIG_FILE = Path(__file__).resolve().parent / "app_settings_tower.json"
DOWNLOAD_TEMP_DIR = Path(__file__).resolve().parent / "tower_data_inbox_temp"
DOWNLOAD_TEMP_DIR.mkdir(parents=True, exist_ok=True)

def load_tower_config() -> Dict[str, Any]:
    """Loads the tower's configuration from a JSON file."""
    if not TOWER_CONFIG_FILE.exists():
        default_config = {
            "server_api_url": "http://127.0.0.1:8000",
            "tower_api_key": "BITTE_DEINEN_GEHEIMEN_API_KEY_HIER_EINFUEGEN",
            "project_name": "last_strawberry",
            "tower_db_path": "",
            "training_hyperparameters": {
                "epochs": 1,
                "batch_size": 1,
                "gradient_accumulation": 8,
                "learning_rate": 2e-4,
                "max_seq_length": 1024
            }
        }
        try:
            with TOWER_CONFIG_FILE.open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            print(f"'{TOWER_CONFIG_FILE}' wurde erfolgreich erstellt.")
            print("\n!!! WICHTIG: Bitte öffne die Datei und ersetze den Platzhalter für 'tower_api_key' !!!")
        except Exception as e:
            print(f"Fehler beim Erstellen der Konfigurationsdatei: {e}")
        logger.critical(f"Tower config file not found at '{TOWER_CONFIG_FILE}'. it was create.")
        sys.exit(1)
    try:
        with TOWER_CONFIG_FILE.open("r", encoding="utf-8") as f:
            config = json.load(f)
        logger.info(f"Tower configuration loaded from '{TOWER_CONFIG_FILE}'.")
        return config
    except Exception as e:
        logger.error(f"Error loading tower config: {e}", exc_info=True)
        sys.exit(1)

def list_all_new_batches_from_server(server_url: str, api_key: str) -> Optional[List[str]]:
    """Fetches the list of ALL new, unprocessed data batches from the server."""
    list_url = f"{server_url.rstrip('/')}/data/list_new_batches"
    headers = {"X-API-Key": api_key, "accept": "application/json"}
    try:
        logger.info(f"Fetching list of all new batch files from {list_url}...")
        response = requests.get(list_url, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        batch_files = data.get("new_batch_files", [])
        logger.info(f"Server reported {len(batch_files)} new batch files in total.")
        return batch_files
    except requests.RequestException as e:
        logger.error(f"Error fetching batch list: {e}", exc_info=True)
        return None

def download_batch_file(server_url: str, api_key: str, world_name: str, filename: str) -> Optional[Path]:
    """Downloads a single batch file and returns its local path."""
    download_url = f"{server_url.rstrip('/')}/data/download_batch/{world_name}/{filename}"
    headers = {"X-API-Key": api_key}
    # Create a world-specific subdirectory to avoid filename clashes
    world_temp_dir = DOWNLOAD_TEMP_DIR / world_name
    world_temp_dir.mkdir(exist_ok=True)
    local_path = world_temp_dir / filename
    
    try:
        logger.info(f"Downloading '{filename}' for world '{world_name}'...")
        with requests.get(download_url, headers=headers, stream=True, timeout=120) as r:
            r.raise_for_status()
            with local_path.open("wb") as f:
                shutil.copyfileobj(r.raw, f)
        logger.info(f"Successfully downloaded to '{local_path}'.")
        return local_path
    except requests.RequestException as e:
        logger.error(f"Failed to download '{filename}': {e}", exc_info=True)
        if local_path.exists():
            local_path.unlink()
        return None

def group_files_by_world(batch_files: List[str]) -> Dict[str, List[str]]:
    """Groups a list of 'world/file' paths into a dictionary."""
    worlds = {}
    for path_str in batch_files:
        try:
            project_name, world_name, filename = path_str.split('/', 2)
            logger.info(world_name)
            if world_name not in worlds:
                worlds[world_name] = []
            worlds[world_name].append(filename)

        except ValueError:
            logger.warning(f"Invalid batch path format from server: '{path_str}'. Skipping.")
    return worlds

def import_data_into_tower_db(db_manager: DatabaseManager, world_id: int, file_path: Path) -> bool:
    """
    Imports data from a single JSONL file into the tower's database for a specific world.
    This is a placeholder for the actual import logic.
    """
    try:
        logger.info(f"Importing data from '{file_path.name}' for world_id {world_id} into tower database...")
        stats = db_manager.import_events_from_jsonl(world_id, file_path)
        logger.info(f"Import successful.'{stats}")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to import '{file_path.name}' as processed: {e}", exc_info=True)
        return False

def mark_batch_processed_on_server(server_url: str, api_key: str, world_name: str, filename: str) -> bool:
    """Notifies the server that a batch has been successfully processed."""
    mark_url = f"{server_url.rstrip('/')}/data/mark_batch_processed/{world_name}/{filename}"
    headers = {"X-API-Key": api_key}
    try:
        response = requests.post(mark_url, headers=headers, timeout=30)
        response.raise_for_status()
        logger.info(f"Successfully marked '{filename}' as processed on server.")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to mark '{filename}' as processed: {e}", exc_info=True)
        return False

def main_data_ingestion() -> Dict[str, Any]:
    """
    Main entry point for the data ingestion process.
    Downloads all new data, sorts it by world, and prepares it for training.
    
    Returns:
        A dictionary mapping world names to their details if they have new data.
    """
    logger.info("--- Starting Data Ingestion Phase (Eingabe) ---")
    try:
        config = load_tower_config()
        server_url = config['server_api_url']
        api_key = config['tower_api_key']
        tower_db_path = config.get("tower_db_path", str(PROJECT_ROOT))
    except (KeyError, FileNotFoundError):
        logger.critical("Configuration is missing or invalid. Aborting.")
        return {}

    all_batch_paths = list_all_new_batches_from_server(server_url, api_key)
    
    if not all_batch_paths:
        logger.info("No new data on the server. Data ingestion complete.")
        return {}

    worlds_with_new_data = group_files_by_world(all_batch_paths)

    DOWNLOAD_TEMP_DIR.mkdir(exist_ok=True)
    
    

    processed_worlds = {}

    for world_name, filenames in worlds_with_new_data.items():
        logger.info(f"--- Processing data for world: {world_name} ---")
        
        tower_db = DatabaseManager(db_path=Path(tower_db_path /  f"{world_name}_laststrawberry.db"))
        tower_db.setup_database() # Ensure tables exist

        world_info = tower_db.get_or_create_world(world_name)
        if not world_info:
            logger.warning(f"World '{world_name}' not found in tower database. It might be a new world. Skipping for now.")
            continue

        world_id = world_info
        all_downloads_successful = True
        
        for filename in filenames:
            local_path = download_batch_file(server_url, api_key, world_name, filename)
            if local_path:
                # Import data into the central tower DB for this world
                if import_data_into_tower_db(tower_db, world_id, local_path):
                    # Mark as processed on server only after successful import
                    mark_batch_processed_on_server(server_url, api_key, world_name, filename)
                else:
                    logger.error(f"Failed to import data from '{filename}' into tower DB. It will be re-downloaded next run.")
                    all_downloads_successful = False
                
                local_path.unlink() # Clean up downloaded file
            else:
                all_downloads_successful = False
        
        if all_downloads_successful:
            processed_worlds[world_name] = world_info

        tower_db.close_connection()
    logger.info("--- Data Ingestion Phase Finished ---")
    return processed_worlds


if __name__ == "__main__":
    worlds_ready_for_training = main_data_ingestion()
    if worlds_ready_for_training:
        print("\nData ingestion complete. The following worlds are ready for training:")
        for name, info in worlds_ready_for_training.items():
            print(f"- {name} (ID: {info['world_id']})")
    else:
        print("\nData ingestion complete. No worlds have new data ready for training.")
