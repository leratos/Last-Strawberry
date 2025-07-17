# test_suite_analysis.py
# -*- coding: utf-8 -*-

"""
Optimierte Testsuite für die KI-Analyse-Phase.
Kann sowohl gegen eine lokale Instanz als auch gegen einen
live Cloud-Dienst getestet werden.
"""

import json
import logging
import sys
import re
import difflib
import asyncio
import httpx
from typing import List, Dict, Any

# Füge das Projektverzeichnis zum Pfad hinzu
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))

# Importiere die Testfälle aus der separaten Datei
from test_data.analysis_test_cases import TEST_CASES
from templates.regeln import ANALYSIS_PROMPT_TEMPLATE

# --- KONFIGURATION ---
# Ändern Sie dies auf "cloud", um gegen den Live-Dienst zu testen.
TEST_TARGET = "local" 
# Ersetzen Sie dies durch Ihre echte Cloud Run Service URL
AI_SERVICE_URL = "https://last-strawberry-ai-service-520324701590.europe-west4.run.app" 

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ALLOWED_FIELDS = {
    "NPC_CREATE": ["command", "name", "backstory", "disposition"],
    "NPC_UPDATE": ["command", "old_name", "new_name"],
    "PLAYER_MOVE": ["command", "location_name"],
    "NPC_MOVE": ["command", "npc_name", "location_name"],
    "PLAYER_STATE_UPDATE": ["command", "updates"],
    "NPC_STATE_UPDATE": ["command", "npc_name", "updates"],
    "ROLL_CHECK": ["command", "attribut", "schwierigkeit"],
}

# --- Hilfsfunktionen für den Vergleich ---

def fuzzy_match(a: str, b: str, threshold=0.82) -> bool:
    """Vergleicht zwei Strings fuzzy (Levenshtein)"""
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio() >= threshold

def command_fuzzy_eq(cmd_a: Dict[str, Any], cmd_b: Dict[str, Any]) -> bool:
    """Vergleicht zwei Befehle fuzzy und prüft auf Feld-Drift."""
    command_type = cmd_a.get('command')
    if not command_type or command_type not in ALLOWED_FIELDS:
        # Wenn der Befehlstyp selbst schon unbekannt ist, schlägt der Test fehl.
        return False
        
    allowed = set(ALLOWED_FIELDS[command_type])
    actual_keys = set(cmd_a.keys())
    
    # Prüfen, ob unerlaubte Felder vorhanden sind.
    extra_fields = actual_keys - allowed
    if extra_fields:
        # Dieser Test schlägt fehl, wenn die KI ein Feld wie "mood" erfindet.
        return False
    if cmd_a.get('command') != cmd_b.get('command'):
        return False
    
    # Prüfe alle Schlüssel, die exakt oder sehr ähnlich sein müssen
    for key in ['name', 'old_name', 'new_name', 'location_name', 'attribut']:
        if key in cmd_b and not fuzzy_match(cmd_a.get(key, ""), cmd_b.get(key, "")):
            return False
            
    # Für Zustandsänderungen, prüfe ob die Schlüssel übereinstimmen
    if cmd_b.get("command") in ["PLAYER_STATE_UPDATE", "NPC_STATE_UPDATE"]:
        if "updates" in cmd_b:
            if not isinstance(cmd_a.get("updates"), dict) or set(cmd_b["updates"].keys()) != set(cmd_a["updates"].keys()):
                return False

    return True

def match_command_lists_fuzzy(actual: List[Dict[str, Any]], expected: List[Dict[str, Any]]) -> tuple[bool, str]:
    """Vergleicht zwei Listen von Befehlen unsortiert und fuzzy."""
    if len(actual) != len(expected):
        return False, f"Anzahl der Befehle stimmt nicht: Erwartet {len(expected)}, erhalten {len(actual)}"
    
    matched_expected = [False] * len(expected)
    unmatched_actual = []

    for a_cmd in actual:
        found_match = False
        for i, e_cmd in enumerate(expected):
            if not matched_expected[i] and command_fuzzy_eq(a_cmd, e_cmd):
                matched_expected[i] = True
                found_match = True
                break
        if not found_match:
            unmatched_actual.append(a_cmd)
            
    if unmatched_actual:
        return False, f"Unerwarteter Befehl in KI-Ausgabe: {json.dumps(unmatched_actual[0], indent=2)}"
        
    return True, ""


class AnalysisTestSuite:
    def __init__(self):
        self.results = {"success": 0, "failed": 0, "details": []}
        self.inference_service = None

        if TEST_TARGET == "local":
            from class_folder.core.inference_service import InferenceService
            from peft import PeftModel
            logger.info("Initialisiere LOKALEN KI-Dienst für die Testsuite...")
            self.inference_service = InferenceService()
            if not self.inference_service.base_model_loaded:
                logger.error("Lokale KI konnte nicht geladen werden."); sys.exit(1)
            
            analysis_adapter_path = self.inference_service._find_specific_adapter("analysis_adapter")
            if analysis_adapter_path:
                self.inference_service.model = PeftModel.from_pretrained(self.inference_service.base_model, analysis_adapter_path)
                logger.info(f"Lokaler Analyse-Adapter von '{analysis_adapter_path}' geladen.")
            else:
                logger.warning("Kein lokaler Analyse-Adapter gefunden. Teste gegen Basismodell.")
        else:
            logger.info(f"Testsuite für CLOUD-Ziel konfiguriert: {AI_SERVICE_URL}")

    def _format_llama3_prompt(self, system_prompt: str) -> str:
        return (f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
                f"{system_prompt.strip()}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n")

    def _build_full_prompt(self, case: Dict[str, Any]) -> str:
        # Baut den finalen Prompt, der an die KI gesendet wird
        char_attributes = "Stärke, Geschicklichkeit, Konstitution, Intelligenz, Weisheit, Charisma"
        system_prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            player_command=case["player_command"],
            narrative_text=case["narrative_text"],
            player_name=case["player_name"],
            npc_context=case["npc_context"],
            char_attributes=char_attributes
        )
        return self._format_llama3_prompt(system_prompt)

    async def run_cloud_analysis(self, full_prompt: str) -> List[Dict[str, Any]]:
        """Sendet eine Anfrage an den Cloud-Dienst."""
        request_data = {"prompt": full_prompt, "world_name": "test_world", "adapter_type": "ANALYSIS"}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(f"{AI_SERVICE_URL}/generate", json=request_data)
                response.raise_for_status()
                ai_response = response.json()["generated_text"]
        except Exception as e:
            logger.error(f"Fehler bei der Cloud-Anfrage: {e}")
            return [{"error": str(e)}]
        
        try:
            match = re.search(r'\[.*\]', ai_response, re.DOTALL)
            return json.loads(match.group(0)) if match else []
        except json.JSONDecodeError:
            logger.error(f"Cloud-Antwort war kein valides JSON: {ai_response}")
            return []

    def run_local_analysis(self, full_prompt: str) -> List[Dict[str, Any]]:
        """Führt die Analyse mit dem lokalen Dienst durch."""
        ai_response = self.inference_service.generate_story_response(full_prompt)
        try:
            match = re.search(r'\[.*\]', ai_response, re.DOTALL)
            return json.loads(match.group(0)) if match else []
        except json.JSONDecodeError:
            logger.error(f"Lokale Antwort war kein valides JSON: {ai_response}")
            return []

    def _create_training_example(self, case: Dict[str, Any], file_handle):
        """Formatiert einen Testfall als Trainingsbeispiel und schreibt ihn in eine Datei."""
        full_prompt = self._build_full_prompt(case)
        assistant_output = json.dumps(case["expected_commands"], indent=2, ensure_ascii=False)
        
        # Entferne den leeren Assistant-Teil vom Ende des Prompts
        prompt_for_training = full_prompt.strip()
        
        training_text = f"{prompt_for_training}{assistant_output}<|eot_id|>"
        file_handle.write(json.dumps({"text": training_text}) + "\n")

    async def run_all_tests(self):
        logger.info(f"Starte Testlauf mit {len(TEST_CASES)} Testfällen gegen Ziel: '{TEST_TARGET.upper()}'...")
        output_dataset_path = Path("analysis_dataset.jsonl")
        
        with output_dataset_path.open("w", encoding="utf-8") as f:
            for i, case in enumerate(TEST_CASES):
                test_name = case["name"]
                logger.info(f"--- Führe Testfall {i+1}/{len(TEST_CASES)} aus: {test_name} ---")
                
                full_prompt = self._build_full_prompt(case)
                
                if TEST_TARGET == "local":
                    actual_commands = self.run_local_analysis(full_prompt)
                else:
                    actual_commands = await self.run_cloud_analysis(full_prompt)
                
                expected_commands = case["expected_commands"]
                
                ok, detail = match_command_lists_fuzzy(actual_commands, expected_commands)
                if ok:
                    self.results["success"] += 1
                    logger.info(f"✅ ERFOLGREICH: {test_name}")
                    self.results["details"].append({"name": test_name, "status": "ERFOLG"})
                else:
                    self.results["failed"] += 1
                    logger.error(f"❌ FEHLGESCHLAGEN: {test_name}")
                    self.results["details"].append({
                        "name": test_name, "status": "FEHLER", "reason": detail,
                        "expected": expected_commands, "actual": actual_commands
                    })
                
                # Schreibe das Trainingsbeispiel, unabhängig vom Ergebnis
                self._create_training_example(case, f)
        
        logger.info(f"Trainings-Datensatz '{output_dataset_path}' wurde erfolgreich erstellt.")
        self.print_summary()

    def print_summary(self):
        """Gibt eine detaillierte Zusammenfassung der Testergebnisse aus."""
        total = self.results["success"] + self.results["failed"]
        print("\n" + "="*60)
        print(" " * 18 + "TESTERGEBNIS-ZUSAMMENFASSUNG")
        print("="*60)
        print(f"  Gesamte Testfälle: {total}")
        print(f"  ✅ Erfolgreich:      {self.results['success']}")
        print(f"  ❌ Fehlgeschlagen:   {self.results['failed']}")
        print("="*60 + "\n")
        
        if self.results["failed"] > 0:
            print("Details der fehlgeschlagenen Tests:")
            for detail in self.results["details"]:
                if detail["status"] == "FEHLER":
                    print(f"\n--- {detail['name']} ---")
                    print(f"  > Grund: {detail['reason']}")
                    print(f"  > Erwartet:\n{json.dumps(detail['expected'], indent=4, ensure_ascii=False)}")
                    print(f"  > Erhalten:\n{json.dumps(detail['actual'], indent=4, ensure_ascii=False)}")

if __name__ == "__main__":
    suite = AnalysisTestSuite()
    asyncio.run(suite.run_all_tests())
