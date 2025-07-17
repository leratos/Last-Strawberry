# cronjob/tower_daily_workflow.py
# -*- coding: utf-8 -*-
"""
Main orchestration script for the Tower's automated workflow (EVA-Process).
This script is intended to be run as a scheduled task (e.g., a cron job).
"""
import logging
from pathlib import Path
import datetime
import sys
import shutil

# --- Project-specific Imports ---
# Ensure the project root is in the system path to allow for package imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import the main functions from the other tower scripts
try:
    from tower_data_processor import main_data_ingestion, load_tower_config
    from tower_model_trainer import main_training_for_world
    from tower_model_uploader import main_upload_for_world
except ImportError as e:
    logging.critical(f"Could not import a required tower module. Error: {e}")
    sys.exit(1)

# --- Logging Setup ---
LOG_FILE_PATH = Path(__file__).resolve().parent / "tower_workflow.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE_PATH, mode="a"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

def main_workflow():
    """Main entry point for the automated EVA-Process."""
    logger.info(f"===== Starting Last-Strawberry Tower Workflow: {datetime.datetime.now()} =====")
    
    # --- EINGABE (Input) ---
    # The data processor will download new data and return a dictionary of
    # worlds that are ready for training.
    logger.info("--- Phase 1: Data Ingestion (Eingabe) ---")
    worlds_to_train = main_data_ingestion()

    if not worlds_to_train:
        logger.info("No worlds have new data ready for training. Workflow finished.")
        logger.info(f"===== Workflow Finished: {datetime.datetime.now()} =====")
        return

    logger.info(f"Worlds ready for training: {list(worlds_to_train.keys())}")

    # --- VERARBEITUNG & AUSGABE (Process & Output) ---
    # Now, loop through each world that has new data and run the V & A phases.
    for world_name, world_info in worlds_to_train.items():
        logger.info(f"--- Starting EVA-Cycle for World: '{world_name}' ---")
        
        # --- VERARBEITUNG (Training) ---
        logger.info(f"--- Phase 2: Model Training (Verarbeitung) for '{world_name}' ---")
        trained_adapter_directory = main_training_for_world(
            world_id=world_info,
            world_name=world_name
        )

        if not trained_adapter_directory:
            logger.error(f"Training failed for '{world_name}'. Skipping upload. Moving to next world.")
            continue

        # --- AUSGABE (Upload) ---
        logger.info(f"--- Phase 3: Model Upload (Ausgabe) for '{world_name}' ---")
        upload_successful = main_upload_for_world(
            trained_adapter_path=trained_adapter_directory,
            world_name=world_name
        )

        if upload_successful:
            logger.info(f"Successfully trained and uploaded new model for '{world_name}'.")
        else:
            logger.error(f"Model upload failed for '{world_name}'. The new adapter is available locally but was not sent to the server.")
        
        # Clean up the local adapter directory after attempting upload
        logger.info(f"Cleaning up local adapter directory: {trained_adapter_directory}")
        shutil.rmtree(trained_adapter_directory)

        logger.info(f"--- EVA-Cycle for World '{world_name}' finished. ---")

    logger.info(f"===== Tower Workflow Finished: {datetime.datetime.now()} =====")


if __name__ == "__main__":
    main_workflow()
