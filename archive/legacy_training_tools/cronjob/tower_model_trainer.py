# cronjob/tower_model_trainer.py
# -*- coding: utf-8 -*-
"""
Handles the fine-tuning process for a single world.
Part 2 of the EVA-Process: The 'V' (Verarbeitung/Process) phase.
"""
import logging
from pathlib import Path
import datetime
import sys
import shutil
import gc
import torch

# --- Project-specific Imports ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from class_folder.core.database_manager import DatabaseManager
    from class_folder.core.hf_fine_tuner import HFFineTuner
    from tower_data_processor import load_tower_config # Re-use config loader
except ImportError as e:
    logging.critical(f"Could not import a required class. Error: {e}")
    sys.exit(1)

logger = logging.getLogger(__name__)

# --- Global Paths ---
ADAPTER_OUTPUT_BASE_DIR = PROJECT_ROOT / "trained_adapters_output"
ADAPTER_OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)
TOWER_DB_PATH = PROJECT_ROOT 

def cleanup_old_adapters(world_name: str):
    """Removes old adapter folders for a specific world to save space."""
    world_name_safe = world_name.replace(" ", "_")
    world_adapters = [d for d in ADAPTER_OUTPUT_BASE_DIR.iterdir() if d.is_dir() and d.name.startswith(world_name_safe)]
    
    if len(world_adapters) <= 1:
        return # Keep the latest one

    world_adapters.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old_adapter in world_adapters[1:]:
        logger.info(f"Cleaning up old adapter: {old_adapter.name}")
        shutil.rmtree(old_adapter)

def main_training_for_world(world_id: int, world_name: str) -> Path | None:
    """
    Main function to start the training process for a specific world.
    Returns the path to the trained adapter on success, otherwise None.
    """
    fine_tuner = None
    db_manager = DatabaseManager(db_path=TOWER_DB_PATH / f"{world_name}_laststrawberry.db")
    
    try:
        logger.info(f"=== Starting Fine-Tuning for World: '{world_name}' (ID: {world_id}) ===")

        events_for_training = db_manager.get_events_for_review(label='gut (Training)', world_id=world_id)
        if not events_for_training:
            logger.warning(f"No events marked as 'gut (Training)' found for world '{world_name}'. Skipping training.")
            return None

        logger.info(f"Found {len(events_for_training)} high-quality events for training.")

        config = load_tower_config()
        training_hyperparams = config.get("training_hyperparameters", {})
        
        output_dir = ADAPTER_OUTPUT_BASE_DIR / f"{world_name.replace(' ', '_')}_adapter_{datetime.datetime.now().strftime('%Y%m%d-%H%M')}"
        training_hyperparams['output_dir'] = str(output_dir)

        fine_tuner = HFFineTuner(
            db_manager=db_manager,
            training_config=training_hyperparams,
            world_id=world_id
        )
        
        success = fine_tuner.run_fine_tuning()
        
        if success:
            logger.info(f"Training for world '{world_name}' successful!")
            cleanup_old_adapters(world_name)
            return output_dir
        else:
            logger.error(f"Training for world '{world_name}' failed.")
            return None

    except Exception as e:
        logger.error(f"An unexpected error occurred during the main training function: {e}", exc_info=True)
        return None
    finally:
        if db_manager:
            db_manager.close_connection()
        # Aggressive cleanup to free VRAM
        if fine_tuner:
            del fine_tuner.model
            del fine_tuner.tokenizer
            del fine_tuner
        gc.collect()
        torch.cuda.empty_cache()
