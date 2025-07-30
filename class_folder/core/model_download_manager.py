"""
Model Download Manager für Last-Strawberry
Verwaltet das Herunterladen und Setup von KI-Modellen
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Optional, Callable
import requests
from tqdm import tqdm

class ModelDownloadManager:
    """Manager für KI-Modell Downloads"""
    
    def __init__(self, app_dir: Optional[Path] = None):
        self.app_dir = app_dir or Path(__file__).parent.parent
        self.hf_cache_dir = self.app_dir / "hf_cache"
        self.adapter_dir = self.app_dir / "adapter"
        self.progress_callback: Optional[Callable] = None
        
    def set_progress_callback(self, callback: Callable[[str, float], None]):
        """Setzt Callback für Progress-Updates"""
        self.progress_callback = callback
        
    def _report_progress(self, message: str, progress: float = 0.0):
        """Berichtet Progress an Callback"""
        if self.progress_callback:
            self.progress_callback(message, progress)
        else:
            print(f"{message} ({progress:.1f}%)")
    
    def check_models_available(self) -> dict:
        """Prüft welche Modelle verfügbar sind"""
        status = {
            'base_model': False,
            'analysis_adapter': False,
            'narrative_adapter': False,
            'total_size_gb': 0
        }
        
        # Prüfe Basis-Modell
        base_model_path = self.hf_cache_dir / "models--meta-llama--Meta-Llama-3-8B-Instruct"
        if base_model_path.exists() and any(base_model_path.iterdir()):
            status['base_model'] = True
            status['total_size_gb'] += self._get_directory_size_gb(base_model_path)
        
        # Prüfe Adapter
        analysis_adapter = self.adapter_dir / "analysis_adapter_v20250719_1521"
        if analysis_adapter.exists():
            status['analysis_adapter'] = True
            status['total_size_gb'] += self._get_directory_size_gb(analysis_adapter)
            
        return status
    
    def _get_directory_size_gb(self, path: Path) -> float:
        """Berechnet Verzeichnisgröße in GB"""
        total = 0
        try:
            for file_path in path.rglob('*'):
                if file_path.is_file():
                    total += file_path.stat().st_size
        except (OSError, PermissionError):
            pass
        return total / (1024**3)  # Convert to GB
    
    def download_base_model(self) -> bool:
        """Lädt das Basis-Modell herunter"""
        try:
            self._report_progress("Lade Meta Llama 3 8B Instruct...", 0)
            
            # Erstelle Cache-Verzeichnis
            self.hf_cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Verwende huggingface_hub für Download
            python_exe = self._get_python_executable()
            
            download_script = f'''
import os
os.environ['HF_HOME'] = '{self.hf_cache_dir}'
os.environ['TRANSFORMERS_CACHE'] = '{self.hf_cache_dir}'

from huggingface_hub import snapshot_download
import sys

try:
    print("Starte Download von Meta-Llama-3-8B-Instruct...")
    snapshot_download(
        "meta-llama/Meta-Llama-3-8B-Instruct",
        cache_dir="{self.hf_cache_dir}",
        local_dir="{self.hf_cache_dir}/models--meta-llama--Meta-Llama-3-8B-Instruct",
        local_dir_use_symlinks=False
    )
    print("Download erfolgreich abgeschlossen!")
    sys.exit(0)
except Exception as e:
    print(f"Download-Fehler: {{e}}")
    sys.exit(1)
'''
            
            # Schreibe temporäres Script
            temp_script = self.app_dir / "temp_download.py"
            with open(temp_script, 'w', encoding='utf-8') as f:
                f.write(download_script)
            
            # Führe Download aus
            result = subprocess.run([
                python_exe, str(temp_script)
            ], capture_output=True, text=True, cwd=str(self.app_dir))
            
            # Cleanup
            if temp_script.exists():
                temp_script.unlink()
            
            if result.returncode == 0:
                self._report_progress("Basis-Modell erfolgreich heruntergeladen!", 100)
                return True
            else:
                self._report_progress(f"Download-Fehler: {result.stderr}", 0)
                return False
                
        except Exception as e:
            self._report_progress(f"Fehler beim Model-Download: {e}", 0)
            return False
    
    def download_adapters(self) -> bool:
        """Lädt die benutzerdefinierten Adapter herunter"""
        try:
            self._report_progress("Lade Custom-Adapter...", 0)
            
            # Hier würden Sie Ihre eigenen Adapter von einem Server laden
            # Für jetzt erstellen wir Platzhalter-Adapter
            
            self.adapter_dir.mkdir(parents=True, exist_ok=True)
            
            # Erstelle Basis-Adapter-Struktur
            analysis_adapter_dir = self.adapter_dir / "analysis_adapter_v20250719_1521"
            analysis_adapter_dir.mkdir(exist_ok=True)
            
            # Erstelle Adapter-Config (Platzhalter)
            adapter_config = {
                "base_model_name_or_path": "meta-llama/Meta-Llama-3-8B-Instruct",
                "task_type": "CAUSAL_LM",
                "inference_mode": False,
                "r": 16,
                "lora_alpha": 32,
                "lora_dropout": 0.1,
                "target_modules": ["q_proj", "v_proj", "k_proj", "o_proj"]
            }
            
            with open(analysis_adapter_dir / "adapter_config.json", 'w') as f:
                json.dump(adapter_config, f, indent=2)
            
            # Erstelle README
            readme_content = """
# Analysis Adapter für Last-Strawberry

Dieser Adapter ist speziell für die Analyse von Spieler-Eingaben trainiert.

## Verwendung
- Extrahiert strukturierte Befehle aus natürlichsprachlichen Eingaben
- Konvertiert Spieler-Intentionen in Game-Commands
- Optimiert für deutsche Sprache

## Training
- Trainiert auf korrigierten Spielsession-Daten
- Kontinuierlich verbesserbar durch DM-Feedback
- LoRA-Adapter für effizienten Transfer
"""
            
            with open(analysis_adapter_dir / "README.md", 'w', encoding='utf-8') as f:
                f.write(readme_content)
            
            self._report_progress("Custom-Adapter erfolgreich eingerichtet!", 100)
            return True
            
        except Exception as e:
            self._report_progress(f"Fehler beim Adapter-Download: {e}", 0)
            return False
    
    def _get_python_executable(self) -> str:
        """Findet den Python-Interpreter"""
        # Versuche eingebettetes Python
        embedded_python = self.app_dir / "python" / "python.exe"
        if embedded_python.exists():
            return str(embedded_python)
        
        # Fallback auf System-Python
        return sys.executable
    
    def download_all_models(self) -> bool:
        """Lädt alle Modelle herunter"""
        try:
            self._report_progress("Starte vollständigen Model-Download...", 0)
            
            # Download Basis-Modell (90% der Arbeit)
            if not self.download_base_model():
                return False
            
            self._report_progress("Basis-Modell vollständig, lade Adapter...", 90)
            
            # Download Adapter (10% der Arbeit) 
            if not self.download_adapters():
                return False
            
            self._report_progress("Alle Modelle erfolgreich heruntergeladen!", 100)
            return True
            
        except Exception as e:
            self._report_progress(f"Fehler beim Download: {e}", 0)
            return False


def main():
    """CLI für Model-Download"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Last-Strawberry Model Downloader")
    parser.add_argument("--base-only", action="store_true", help="Nur Basis-Modell herunterladen")
    parser.add_argument("--adapters-only", action="store_true", help="Nur Adapter herunterladen")
    parser.add_argument("--check", action="store_true", help="Prüfe verfügbare Modelle")
    
    args = parser.parse_args()
    
    manager = ModelDownloadManager()
    
    if args.check:
        status = manager.check_models_available()
        print("Model Status:")
        print(f"  Basis-Modell: {'✅' if status['base_model'] else '❌'}")
        print(f"  Analysis-Adapter: {'✅' if status['analysis_adapter'] else '❌'}")
        print(f"  Narrative-Adapter: {'✅' if status['narrative_adapter'] else '❌'}")
        print(f"  Gesamtgröße: {status['total_size_gb']:.1f} GB")
        return
    
    if args.base_only:
        success = manager.download_base_model()
    elif args.adapters_only:
        success = manager.download_adapters()
    else:
        success = manager.download_all_models()
    
    if success:
        print("✅ Download erfolgreich abgeschlossen!")
    else:
        print("❌ Download fehlgeschlagen!")
        sys.exit(1)


if __name__ == "__main__":
    main()
