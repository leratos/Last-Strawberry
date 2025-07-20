# class/core/inference_service.py
# -*- coding: utf-8 -*-

"""
Manages the loading of the Hugging Face model and tokenizer for inference,
and provides methods to generate story text.
This version includes logic to automatically load the latest LoRA adapter.
"""

import logging
import os
from pathlib import Path
from typing import Optional

# Configuration and optional libraries
from . import game_config as config
import torch

try:
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        pipeline
    )
    from peft import PeftModel
    from huggingface_hub import HfFolder
    HF_LIBRARIES_AVAILABLE = True
except ImportError:
    HF_LIBRARIES_AVAILABLE = False
    AutoModelForCausalLM = type('AutoModelForCausalLM', (object,), {})
    AutoTokenizer = type('AutoTokenizer', (object,), {})
    BitsAndBytesConfig = type('BitsAndBytesConfig', (object,), {})
    PeftModel = type('PeftModel', (object,), {})
    pipeline = None

logger = logging.getLogger(__name__)


class InferenceService:
    """Handles AI model loading and world-specific adapter application."""

    def __init__(self):
        """Initializes the service and loads the model."""
        self.base_model: Optional[AutoModelForCausalLM] = None
        self.model: Optional[AutoModelForCausalLM] = None
        self.tokenizer: Optional[AutoTokenizer] = None
        self.pipe: Optional[pipeline] = None
        self.base_model_loaded = False
        self.device = config.DEVICE
        self.load_status = "Not Loaded"

        if not HF_LIBRARIES_AVAILABLE:
            self.load_status = "Error: Required libraries (transformers, peft) not found."
            logger.error(self.load_status)
            return

        self._load_base_model_and_tokenizer()
        self._initialize_pipeline()

    def _find_adapter_for_world(self, world_name: str) -> Optional[str]:
        """Finds the most recent adapter for a specific world name."""
        adapter_base_dir = Path("./trained_adapters")
        if not adapter_base_dir.exists():
            return None
        
        world_name_safe = world_name.replace(" ", "_")
        world_adapters = [d for d in adapter_base_dir.iterdir() if d.is_dir() and d.name.startswith(world_name_safe)]
        
        if not world_adapters:
            return None
            
        latest_adapter = max(world_adapters, key=os.path.getctime)
        logger.info(f"Found specific adapter for world '{world_name}': {latest_adapter}")
        return str(latest_adapter)

    def _load_base_model_and_tokenizer(self):
        """Loads only the base model and tokenizer initially."""
        if self.base_model_loaded:
            return

        import os
        auth_token = os.getenv("HF_AUTH_TOKEN")
        if not auth_token:
            logger.info("HF_AUTH_TOKEN nicht als Umgebungsvariable gefunden. Versuche HfFolder...")
            from huggingface_hub import HfFolder
            auth_token = HfFolder.get_token()

        if not auth_token:
            self.load_status = "Error: Hugging Face token not found."
            logger.error(self.load_status)
            return

        logger.info(f"Loading base model: {config.HF_BASE_MODEL_NAME}...")
        self.load_status = "Loading base model..."
        
        try:
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=config.BNB_LOAD_IN_4BIT,
                bnb_4bit_quant_type=config.BNB_4BIT_QUANT_TYPE,
                bnb_4bit_compute_dtype=config.BNB_4BIT_COMPUTE_DTYPE,
                bnb_4bit_use_double_quant=config.BNB_4BIT_USE_DOUBLE_QUANT,
            )

            self.base_model = AutoModelForCausalLM.from_pretrained(
                config.HF_BASE_MODEL_NAME,
                quantization_config=bnb_config,
                device_map=self.device,
                trust_remote_code=True,
                cache_dir="./hf_cache",
                token=auth_token,
            )
            self.model = self.base_model

            self.tokenizer = AutoTokenizer.from_pretrained(
                config.HF_BASE_MODEL_NAME,
                token=auth_token,
                use_fast=False
            )
            
            self.load_status = f"Base model '{config.HF_BASE_MODEL_NAME}' loaded."
            logger.info(self.load_status)
            self.base_model_loaded = True

        except Exception as e:
            self.load_status = f"Error loading base model: {e}"
            logger.error(self.load_status, exc_info=True)
            self.base_model = None
            self.model = None
            self.tokenizer = None
    
    def _initialize_pipeline(self):
        """Initializes the text-generation pipeline once."""
        if self.model and self.tokenizer and not self.pipe:
            logger.info("Initializing text-generation pipeline...")
            self.pipe = pipeline(
                "text-generation",
                model=self.model,
                tokenizer=self.tokenizer,
                torch_dtype=config.BNB_4BIT_COMPUTE_DTYPE,
                device_map=self.device,
            )
            logger.info("Pipeline initialized successfully.")

    def _find_specific_adapter(self, adapter_name_part: str) -> Optional[str]:
        """Findet den neuesten Adapter, der einen bestimmten Text im Namen enthält."""
        adapter_base_dir = Path("./adapter")
        if not adapter_base_dir.exists():
            return None
        
        # Findet alle Ordner, die z.B. "analysis_adapter" enthalten
        matching_adapters = [d for d in adapter_base_dir.iterdir() if d.is_dir() and adapter_name_part in d.name]
        
        if not matching_adapters:
            logger.warning(f"Kein '{adapter_name_part}' Adapter gefunden.")
            return None
            
        latest_adapter = max(matching_adapters, key=os.path.getctime)
        logger.info(f"Found specific adapter '{adapter_name_part}': {latest_adapter}")
        return str(latest_adapter)

    def switch_to_adapter(self, adapter_type: str, world_name: str):
        """
        Wechselt den aktiven LoRA-Adapter des Modells dynamisch basierend auf der Anfrage.
        """
        logger.info(f"Switching to {adapter_type} adapter for world '{world_name}'...")
        adapter_path = None
        if adapter_type == 'NARRATIVE':
            adapter_path = self._find_adapter_for_world(world_name)
        elif adapter_type == 'ANALYSIS':
            adapter_path = self._find_specific_adapter("analysis_adapter")
        else:
            logger.error(f"Unknown adapter type '{adapter_type}'")
            self.model = self.base_model
            return

        self.model = self.base_model
        self.load_status = "Base model loaded"

        if adapter_path and Path(adapter_path).exists():
            try:
                self.model = PeftModel.from_pretrained(self.base_model, adapter_path)
                self.load_status = f"Model with {adapter_type} adapter loaded from {adapter_path}"
                logger.info(self.load_status)
            except Exception as e:
                logger.error(f"Failed to load adapter from {adapter_path}: {e}", exc_info=True)
                self.load_status = f"Error loading {adapter_type} adapter. Using base model."
        else:
            logger.info(f"No adapter path found for {adapter_type} and world '{world_name}'. Using base model.")
        
        self.pipe.model = self.model
        self.model.eval()

    def generate_story_response(self, prompt: str) -> str:
        """
        Generates a story response from the AI based on a given prompt.
        """
        if not self.pipe:
            return "Fehler: Die KI-Pipeline ist nicht initialisiert."

        logger.info("Generating AI response...")
        try:
            model_max_length = self.model.config.max_position_embeddings
            inputs = self.tokenizer(prompt, return_tensors="pt")
            prompt_tokens = inputs['input_ids'].shape[1]
            safety_buffer = 150
            max_new_tokens_dynamic = model_max_length - prompt_tokens - safety_buffer
            
            if max_new_tokens_dynamic <= 0:
                logger.error(f"Prompt is too long ({prompt_tokens} tokens) for the model to generate a response.")
                return "[Fehler: Der Kontext der Geschichte ist zu lang geworden.]"

            terminators = [
                self.pipe.tokenizer.eos_token_id,
                self.pipe.tokenizer.convert_tokens_to_ids("<|eot_id|>")
            ]

            sequences = self.pipe(
                prompt,
                max_new_tokens=max_new_tokens_dynamic,
                eos_token_id=terminators,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                repetition_penalty=1.15, 
                pad_token_id=self.pipe.tokenizer.eos_token_id
            )

            if sequences and isinstance(sequences, list):
                full_text = sequences[0]['generated_text']
                
                # VERBESSERTE LOGIK: Finde die Antwort des Assistenten
                assistant_header = "<|start_header_id|>assistant<|end_header_id|>\n"
                assistant_pos = full_text.rfind(assistant_header)

                if assistant_pos != -1:
                    # Nimm den Text nach dem letzten Assistenten-Header
                    response = full_text[assistant_pos + len(assistant_header):].strip()
                    # Entferne das End-Token, falls vorhanden
                    if response.endswith("<|eot_id|>"):
                        response = response[:-len("<|eot_id|>")].strip()
                    
                    if response:
                        logger.info("AI response generated successfully.")
                        return response

            logger.warning("AI did not generate a valid response or the response was empty.")
            return "Die KI schweigt..."

        except Exception as e:
            logger.error(f"Error during AI text generation: {e}", exc_info=True)
            return f"Ein interner Fehler ist in der KI aufgetreten: {e}"
