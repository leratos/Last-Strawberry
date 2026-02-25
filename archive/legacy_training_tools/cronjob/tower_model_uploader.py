# cronjob/tower_model_uploader.py
# -*- coding: utf-8 -*-
"""
Handles packaging and uploading of a trained model adapter to the server.
Part 3 of the EVA-Process: The 'A' (Ausgabe/Output) phase.
"""
import requests
import zipfile
from pathlib import Path
import logging
from typing import Dict, Any

# Import config loader from the data processor script to avoid code duplication
try:
    from tower_data_processor import load_tower_config
except ImportError:
    # Fallback for standalone execution or if import fails
    def load_tower_config(): return {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def create_zip_archive(source_dir: Path, output_zip_path: Path) -> bool:
    """Creates a ZIP archive from the contents of a source directory."""
    if not source_dir.is_dir():
        logger.error(f"Source directory '{source_dir}' not found.")
        return False
    try:
        with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for entry in source_dir.rglob("*"):
                zipf.write(entry, entry.relative_to(source_dir))
        logger.info(f"ZIP archive '{output_zip_path}' created successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to create ZIP archive: {e}", exc_info=True)
        return False

def upload_model_to_server(server_url: str, api_key: str, model_zip_path: Path, world_name: str) -> bool:
    """Uploads a model ZIP file to the world-specific server endpoint."""
    upload_url = f"{server_url.rstrip('/')}/models/upload/{world_name}"
    headers = {"X-API-Key": api_key}
    
    try:
        with model_zip_path.open("rb") as f_zip:
            files = {"model_file": (model_zip_path.name, f_zip, "application/zip")}
            logger.info(f"Uploading model for world '{world_name}' to {upload_url}...")
            
            response = requests.post(upload_url, headers=headers, files=files, timeout=300)
            response.raise_for_status()
            
            logger.info(f"Model upload successful. Server: {response.json()}")
            return True
    except requests.RequestException as e:
        logger.error(f"Failed to upload model for '{world_name}': {e}", exc_info=True)
        return False

def main_upload_for_world(trained_adapter_path: Path, world_name: str) -> bool:
    """
    Main entry point for packaging and uploading a single trained model.
    """
    logger.info(f"=== Starting Upload Process for World: '{world_name}' ===")
    config = load_tower_config()
    server_url = config.get('server_api_url')
    api_key = config.get('tower_api_key')

    if not server_url or not api_key:
        logger.error("Server URL or API Key not found in configuration. Cannot upload.")
        return False

    # Create a temporary zip file in the same directory as this script
    zip_path = Path(__file__).parent / f"{trained_adapter_path.name}.zip"
    
    if create_zip_archive(trained_adapter_path, zip_path):
        success = upload_model_to_server(server_url, api_key, zip_path, world_name)
        zip_path.unlink() # Clean up the zip file after upload attempt
        return success
    else:
        logger.error("Failed to create ZIP archive. Upload aborted.")
        return False
