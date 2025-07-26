# class_folder/core/cloud_inference_service.py
# -*- coding: utf-8 -*-

"""
Cloud-Inference-Service für externe APIs.
Unterstützt sowohl lokale Test-APIs als auch externe Cloud-Services.
"""

import json
import logging
import requests
import time
from pathlib import Path
from typing import Optional, Dict, Any

# Google Cloud Authentication
try:
    from google.oauth2 import id_token, service_account
    from google.auth.transport import requests as google_requests
    import google.auth
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False

logger = logging.getLogger(__name__)


class CloudInferenceService:
    """Cloud-basierter Inference Service für externe APIs."""
    
    def __init__(self, service_url: str, api_key_path: Optional[str] = None, timeout: int = 30):
        """
        Initialisiert den Cloud-Service.
        
        Args:
            service_url: URL des Cloud-Services
            api_key_path: Pfad zur API-Key JSON-Datei (optional für lokale APIs)
            timeout: Timeout für Requests in Sekunden
        """
        self.service_url = service_url.rstrip('/')
        self.api_key_path = api_key_path
        self.timeout = timeout
        self.session = requests.Session()
        
        # Prüfe ob lokale API
        self.is_local = self.service_url.lower().startswith('http://127.0.0.1') or \
                       self.service_url.lower().startswith('http://localhost')
        
        # Prüfe ob Google Cloud Run API
        self.is_google_cloud = 'run.app' in self.service_url.lower()
        
        # Lade API-Key falls erforderlich
        self.api_key_data = None
        if not self.is_local and api_key_path:
            self._load_api_key()
        
        # Setup Google Cloud Authentication falls nötig
        if self.is_google_cloud and not GOOGLE_AUTH_AVAILABLE:
            logger.error("Google Cloud Service erkannt, aber google-auth-library nicht verfügbar!")
            raise ImportError("google-auth-library ist erforderlich für Google Cloud Services")
        
        # Simuliere base_model_loaded für Kompatibilität
        self.base_model_loaded = True
        self.load_status = "Cloud-Service bereit"
        self.current_world_name = "default"  # Standard-Weltname
        self.current_adapter_type = "system_fantasy"  # Standard-Adapter
        
        auth_type = "lokal" if self.is_local else ("Google Cloud" if self.is_google_cloud else "extern")
        logger.info(f"CloudInferenceService initialisiert für {auth_type} API: {self.service_url}")
    
    def _load_api_key(self):
        """Lädt den API-Key aus der JSON-Datei."""
        try:
            if self.api_key_path and Path(self.api_key_path).exists():
                with open(self.api_key_path, 'r', encoding='utf-8') as f:
                    self.api_key_data = json.load(f)
                logger.info("API-Key erfolgreich geladen")
            else:
                logger.warning("Keine API-Key-Datei gefunden oder Pfad nicht angegeben")
        except Exception as e:
            logger.error(f"Fehler beim Laden des API-Keys: {e}")
            raise
    
    def _prepare_headers(self) -> Dict[str, str]:
        """Bereitet die HTTP-Headers vor."""
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Last-Strawberry/5.0'
        }
        
        # Google Cloud Authentication
        if self.is_google_cloud and GOOGLE_AUTH_AVAILABLE:
            try:
                # Zuerst versuche Umgebungsvariable
                auth_req = google_requests.Request()
                identity_token = id_token.fetch_id_token(auth_req, self.service_url)
                headers['Authorization'] = f'Bearer {identity_token}'
                logger.debug("Google Cloud ID-Token über Umgebungsvariable hinzugefügt")
            except Exception as env_error:
                # Falls das fehlschlägt, versuche Service Account aus api_key_path
                if self.api_key_path and Path(self.api_key_path).exists():
                    try:
                        # Setze Umgebungsvariable für Google Auth
                        import os
                        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(self.api_key_path)
                        
                        # Hole default credentials mit ID-Token Support
                        auth_req = google_requests.Request()
                        
                        # Versuche ID-Token mit fetch_id_token zu erstellen
                        identity_token = id_token.fetch_id_token(auth_req, self.service_url)
                        headers['Authorization'] = f'Bearer {identity_token}'
                        logger.debug("Google Cloud ID-Token über default credentials hinzugefügt")
                        
                    except Exception as sa_error:
                        logger.error(f"Service Account Authentication fehlgeschlagen: {sa_error}")
                        
                        # Letzter Fallback: Manuelle Service Account Token-Erstellung
                        try:
                            credentials = service_account.Credentials.from_service_account_file(
                                self.api_key_path,
                                scopes=['https://www.googleapis.com/auth/cloud-platform']
                            )
                            
                            auth_req = google_requests.Request()
                            credentials.refresh(auth_req)
                            
                            # Verwende Access Token (manchmal akzeptiert von Cloud Run)
                            headers['Authorization'] = f'Bearer {credentials.token}'
                            logger.debug("Google Cloud Access-Token als letzter Fallback hinzugefügt")
                            
                        except Exception as final_error:
                            logger.error(f"Alle Authentication-Methoden fehlgeschlagen: {final_error}")
                            raise sa_error
                else:
                    logger.error(f"Google Cloud Authentication fehlgeschlagen: {env_error}")
                    raise env_error
        
        # Andere API-Key Authentication falls nötig
        elif self.api_key_data and not self.is_local:
            # Hier könntest du andere Auth-Methoden implementieren
            pass
        
        return headers
    
    def generate_text(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        """
        Generiert Text über die Cloud-API.
        
        Args:
            prompt: Der Input-Prompt
            max_tokens: Maximale Anzahl Tokens
            temperature: Temperature für Sampling
            
        Returns:
            Generierter Text
        """
        try:
            headers = self._prepare_headers()
            
            # Payload für die API (anpassbar je nach API-Format)
            payload = {
                'prompt': prompt,
                'max_tokens': max_tokens,
                'temperature': temperature,
                'stop': ['<|endoftext|>', '\n\n'],
                'world_name': getattr(self, 'current_world_name', 'default'),  # Erforderlich für Docker API
                'adapter_type': getattr(self, 'current_adapter_type', 'system_fantasy')  # Wichtig für Prompt-Templates
            }
            
            # API-Endpunkt (anpassbar)
            endpoint = f"{self.service_url}/generate"
            
            logger.info(f"Sende Request an {endpoint}")
            logger.info(f"Payload: world_name='{payload['world_name']}', adapter_type='{payload['adapter_type']}', prompt_length={len(prompt)}")
            logger.info(f"PROMPT DEBUG: Erste 200 Zeichen: {prompt[:200]}...")
            response = self.session.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Extrahiere generierten Text (Format abhängig von deiner API)
            if 'generated_text' in result:
                generated_text = result['generated_text']
            elif 'text' in result:
                generated_text = result['text']
            elif 'response' in result:
                generated_text = result['response']
            else:
                # Fallback: Ganzes Result als String
                generated_text = str(result)
            
            logger.info(f"Cloud-API Response erfolgreich: {len(generated_text)} Zeichen")
            return generated_text
            
        except requests.exceptions.Timeout:
            error_msg = f"Timeout bei Cloud-API nach {self.timeout} Sekunden"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        except requests.exceptions.ConnectionError:
            error_msg = f"Verbindungsfehler zur Cloud-API: {self.service_url}"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP-Fehler von Cloud-API: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        except Exception as e:
            error_msg = f"Unerwarteter Fehler bei Cloud-API: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def test_connection(self) -> bool:
        """
        Testet die Verbindung zur Cloud-API mit Kaltstart-Behandlung.
        Für Google Cloud Run Services wird mehrfach versucht, da Kaltstart auftreten kann.
        
        Returns:
            True wenn Verbindung erfolgreich
        """
        try:
            headers = self._prepare_headers()
            
            # Für Google Cloud Services: Erweiterte Kaltstart-Behandlung
            if self.is_google_cloud:
                return self._test_connection_with_warmup(headers)
            
            # Für andere APIs: Standard-Test
            return self._test_connection_standard(headers)
                
        except Exception as e:
            logger.warning(f"Cloud-API Verbindungstest fehlgeschlagen: {e}")
            return False
    
    def _test_connection_with_warmup(self, headers: Dict[str, str]) -> bool:
        """
        Testet Verbindung mit Kaltstart-Behandlung für Google Cloud Run.
        Versucht bis zu 6 Minuten (6 Versuche à 1 Minute) um Kaltstart abzufangen.
        """
        max_attempts = 6  # Maximal 6 Versuche
        wait_time = 60    # 1 Minute zwischen Versuchen
        
        logger.info(f"Teste Google Cloud Run Verbindung (max. {max_attempts} Versuche, {wait_time}s Wartezeit)")
        
        for attempt in range(1, max_attempts + 1):
            logger.info(f"Verbindungsversuch {attempt}/{max_attempts} zu Google Cloud Run...")
            
            # Versuche Health-Check
            if self._try_health_check(headers, timeout=30):  # Längerer Timeout für Kaltstart
                logger.info(f"Google Cloud Run erfolgreich verbunden nach {attempt} Versuch(en)")
                return True
            
            # Falls nicht letzter Versuch, warte vor nächstem Versuch
            if attempt < max_attempts:
                logger.info(f"Kaltstart erkannt, warte {wait_time} Sekunden vor nächstem Versuch...")
                time.sleep(wait_time)
            else:
                logger.warning("Maximale Anzahl Verbindungsversuche erreicht")
        
        return False
    
    def _test_connection_standard(self, headers: Dict[str, str]) -> bool:
        """Standard-Verbindungstest für nicht-Google-Cloud APIs."""
        # Versuche zuerst Health-Check
        if self._try_health_check(headers):
            return True
        
        # Fallback: Teste mit root endpoint
        try:
            response = self.session.get(
                self.service_url,
                headers=headers,
                timeout=5
            )
            if response.status_code in [200, 404]:  # 404 ist OK, bedeutet API läuft
                logger.info("Cloud-API Root-Endpoint erreichbar")
                return True
        except:
            pass
        
        # Letzter Fallback: Mini Test-Generation
        try:
            test_response = self.generate_text("Hi", max_tokens=5, temperature=0.1)
            if test_response:
                logger.info("Cloud-API Test-Generation erfolgreich")
                return True
        except:
            pass
            
        logger.warning("Alle Cloud-API Tests fehlgeschlagen")
        return False
    
    def _try_health_check(self, headers: Dict[str, str], timeout: int = 10) -> bool:
        """
        Versucht einen Health-Check der API.
        
        Args:
            headers: HTTP-Headers für die Anfrage
            timeout: Timeout in Sekunden
            
        Returns:
            True wenn Health-Check erfolgreich
        """
        try:
            health_endpoint = f"{self.service_url}/health"
            logger.debug(f"Versuche Health-Check: {health_endpoint}")
            
            response = self.session.get(
                health_endpoint,
                headers=headers,
                timeout=timeout
            )
            
            if response.status_code == 200:
                logger.info("Cloud-API Health-Check erfolgreich")
                return True
            else:
                logger.debug(f"Health-Check Status: {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            logger.debug(f"Health-Check Timeout nach {timeout}s")
            return False
        except requests.exceptions.ConnectionError:
            logger.debug("Health-Check Verbindungsfehler")
            return False
        except Exception as e:
            logger.debug(f"Health-Check Fehler: {e}")
            return False
    
    def cleanup(self):
        """Räumt Ressourcen auf."""
        if self.session:
            self.session.close()
        logger.info("CloudInferenceService Ressourcen aufgeräumt")
    
    # Kompatibilitätsmethoden für lokalen InferenceService
    def switch_to_adapter(self, adapter_type: str, world_name: str = "default"):
        """Kompatibilitätsmethode - Cloud-Service verwendet andere Adapter-Logik."""
        self.current_world_name = world_name  # Speichere world_name für API-Aufrufe
        
        # 🔧 Übersetze lokale Adapter-Namen zu Cloud-Service Adapter-Namen
        adapter_translation = {
            'system_fantasy': 'NARRATIVE',      # Fantasy-Prompts → Erzählung
            'system_dystopian': 'NARRATIVE',    # Dystopian-Prompts → Erzählung  
            'system_survival_horror': 'NARRATIVE',  # Horror-Prompts → Erzählung
            'system_sci_fi': 'NARRATIVE',       # SciFi-Prompts → Erzählung
            'ANALYSIS': 'ANALYSIS',             # Analyse bleibt Analyse
            'NARRATIVE': 'NARRATIVE'            # Erzählung bleibt Erzählung
        }
        
        # Verwende übersetzten Adapter-Namen für Cloud-API
        cloud_adapter_type = adapter_translation.get(adapter_type, 'NARRATIVE')
        self.current_adapter_type = cloud_adapter_type  # Speichere übersetzten Namen
        
        logger.info(f"Cloud-Service: Adapter-Wechsel von '{adapter_type}' zu '{cloud_adapter_type}' für Welt '{world_name}'")
        # Cloud-Services handhaben Adapter meist über Parameter, nicht über Modell-Switches
    
    def switch_to_base_model(self):
        """Kompatibilitätsmethode - Cloud-Service verwendet andere Modell-Logik."""
        logger.info("Cloud-Service: Wechsel zu Base-Model simuliert")
        # Cloud-Services haben meist ein einheitliches Modell-Interface
        pass
    
    def generate_story_response(self, prompt: str) -> str:
        """
        Kompatibilitätsmethode - leitet zu generate_text weiter.
        Diese Methode wird vom GameManager erwartet.
        """
        logger.info("Cloud-Service: generate_story_response aufgerufen")
        return self.generate_text(prompt, max_tokens=512, temperature=0.7)
