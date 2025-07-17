# class_folder/core/hf_fine_tuner.py
# -*- coding: utf-8 -*-

"""
Handles the fine-tuning process of a Hugging Face model using QLoRA.
This version includes aggressive memory management before saving to prevent system freezes.
"""

import logging
import gc
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

from . import game_config as config
from .database_manager import DatabaseManager

try:
    import torch
    from torch.utils.data import Dataset
    from transformers import (
        AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
        TrainingArguments, Trainer, DataCollatorForLanguageModeling
    )
    from peft import (
        LoraConfig, get_peft_model, prepare_model_for_kbit_training
    )
    from huggingface_hub import HfFolder
    HF_LIBRARIES_AVAILABLE = True
except ImportError as e:
    logging.getLogger(__name__).warning(f"A required ML library is missing: {e}. Fine-tuning will be disabled.")
    HF_LIBRARIES_AVAILABLE = False

logger = logging.getLogger(__name__)

class AnalysisJsonlDataset(Dataset):
    """Eine Dataset-Klasse, die vorformatierte Texte aus einer oder mehreren JSONL-Dateien lädt."""
    def __init__(self, data_paths: List[Path], tokenizer: Any, max_length: int):
        self.tokenizer = tokenizer
        self.max_length = max_length

        self.data = []

        for path in data_paths:
            logger.info(f"Lade und tokenisiere Daten von {path}...")
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    self.data.append(json.loads(line))

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        item_text = self.data[idx]['text']
        tokenized_item = self.tokenizer(
            item_text,
            truncation=True,
            max_length=self.max_length,
            padding="max_length"
        )
        return {
            "input_ids": torch.tensor(tokenized_item["input_ids"]),
            "attention_mask": torch.tensor(tokenized_item["attention_mask"]),
            "labels": torch.tensor(tokenized_item["input_ids"])
        }

class HFFineTuner:
    # This class remains unchanged, except for the _train method
    def __init__(self, db_manager: DatabaseManager, training_config: Dict[str, Any], world_id: int, task_type: str = 'NARRATIVE'):
        if not HF_LIBRARIES_AVAILABLE:
            raise ImportError("Hugging Face libraries are not installed.")

        self.db_manager = db_manager
        self.config = training_config
        self.world_id = world_id
        self.model = None
        self.tokenizer = None
        self.task_type = task_type 
        logger.info(f"HFFineTuner initialized for world_id: {self.world_id} with task: {self.task_type}")


    def _prepare_narrative_data(self) -> Optional[List[Dict[str, str]]]:
        """Holt hochwertige Events aus der DB für das Erzähl-Training."""
        logger.info(f"Fetching high-quality events for NARRATIVE training (world_id {self.world_id})...")
        # get_events_for_review holt als 'gut' bewertete Events
        labels_to_fetch = ['human_corrected', 'gut (Training)']
        all_events = []
        for label in labels_to_fetch:
            events = self.db_manager.get_events_for_review(label=label, world_id=self.world_id)
            all_events.extend(events)
            logger.info(f"Found {len(events)} events with label '{label}'.")

        if not all_events:
            return None

        # Um Duplikate zu vermeiden, falls ein Event mehrere Labels hätte (unwahrscheinlich, aber sicher ist sicher)
        unique_events = {event['event_id']: event for event in all_events}.values()


        formatted_data = []
        for event in unique_events:
            # Llama-3-Format für einen einfachen Dialog-Turn
            text = (f"<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n"
                    f"{event['player_input']}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
                    f"{event['ai_output']}<|eot_id|>")
            formatted_data.append({"text": text})

        logger.info(f"Prepared {len(formatted_data)} unique dialogue entries for narrative training.")
        return formatted_data

    def run_fine_tuning(self) -> bool:
        """Führt das Fine-Tuning basierend auf dem Task-Typ aus."""
        if not self._load_model_and_tokenizer():
            return False

        dataset = None
        max_length = self.config.get("max_seq_length", 1024)

        if self.task_type == 'NARRATIVE':
            training_data = self._prepare_narrative_data()
            if not training_data:
                logger.error("No narrative training data found in DB. Aborting.")
                return False
            dataset = NarrativeDbDataset(training_data, self.tokenizer, max_length)

        elif self.task_type == 'ANALYSIS':
            testsuite_data_path = Path("analysis_dataset.jsonl")
            dm_corrected_data_path = Path("dm_corrected_analysis_dataset.jsonl")
            
            all_data_paths = []
            if testsuite_data_path.exists():
                all_data_paths.append(testsuite_data_path)
                logger.info(f"Gefunden: {testsuite_data_path}")
            if dm_corrected_data_path.exists():
                all_data_paths.append(dm_corrected_data_path)
                logger.info(f"Gefunden: {dm_corrected_data_path}")

            if not all_data_paths:
                logger.error("Keine Trainingsdaten für die Analyse gefunden. Führen Sie die Testsuite oder das Generierungs-Skript aus.")
                return False
            
            # Wir übergeben jetzt eine Liste von Pfaden an das Dataset
            dataset = AnalysisJsonlDataset(data_paths=all_data_paths, tokenizer=self.tokenizer, max_length=max_length)

        else:
            logger.error(f"Unknown task_type: '{self.task_type}'. Aborting.")
            return False

        if not self._train(dataset):
            return False

        logger.info(f"Fine-tuning process for task '{self.task_type}' completed successfully.")
        return True

    def _load_model_and_tokenizer(self) -> bool:
        # This method remains unchanged
        try:
            auth_token = HfFolder.get_token()
            if not auth_token:
                logger.error("Hugging Face token not found. Please log in using 'huggingface-cli login'.")
                return False

            logger.info(f"Loading base model: {config.HF_BASE_MODEL_NAME}")
            
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=config.BNB_LOAD_IN_4BIT,
                bnb_4bit_quant_type=config.BNB_4BIT_QUANT_TYPE,
                bnb_4bit_compute_dtype=config.BNB_4BIT_COMPUTE_DTYPE,
                bnb_4bit_use_double_quant=config.BNB_4BIT_USE_DOUBLE_QUANT,
            )

            self.model = AutoModelForCausalLM.from_pretrained(
                config.HF_BASE_MODEL_NAME,
                quantization_config=bnb_config,
                device_map={"": 0},
                trust_remote_code=True,
                cache_dir="./hf_cache",
                token=auth_token
            )
            
            self.tokenizer = AutoTokenizer.from_pretrained(
                config.HF_BASE_MODEL_NAME,
                cache_dir="./hf_cache",
                use_fast=False,
                token=auth_token
            )
            self.tokenizer.pad_token = self.tokenizer.eos_token

            self.model.gradient_checkpointing_enable()
            self.model = prepare_model_for_kbit_training(self.model)

            lora_config = LoraConfig(
                r=config.LORA_R,
                lora_alpha=config.LORA_ALPHA,
                target_modules=config.LORA_TARGET_MODULES,
                lora_dropout=config.LORA_DROPOUT,
                bias="none",
                task_type=config.LORA_TASK_TYPE,
            )
            self.model = get_peft_model(self.model, lora_config)
            self.model.print_trainable_parameters()
            
            return True
        except Exception as e:
            logger.error(f"Failed to load model or tokenizer: {e}", exc_info=True)
            return False

    def _train(self, dataset: Dataset) -> bool:
        """Sets up and runs the Hugging Face Trainer with proper memory management."""
        if not self.model or not self.tokenizer:
            logger.error("Model or tokenizer not loaded, cannot start training.")
            return False

        output_dir = self.config.get("output_dir", "./lora_adapter")
        
        training_args = TrainingArguments(
            output_dir=output_dir,
            per_device_train_batch_size=self.config.get("batch_size", 1),
            gradient_accumulation_steps=self.config.get("gradient_accumulation", 8),
            learning_rate=self.config.get("learning_rate", 2e-4),
            num_train_epochs=self.config.get("epochs", 1),
            logging_steps=10,
            save_strategy="epoch",
            fp16=True, 
            optim="paged_adamw_8bit",
        )

        trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=dataset,
            tokenizer=self.tokenizer,
            data_collator=DataCollatorForLanguageModeling(self.tokenizer, mlm=False),
        )

        logger.info("Starting training...")
        try:
            trainer.train()
            logger.info("Training process finished.")
            
            # KORREKTE LOGIK: Speicherbereinigung VOR dem Speichern
            logger.info("Freeing up memory before saving adapter...")
            del trainer
            gc.collect()
            torch.cuda.empty_cache()
            
            logger.info("Memory freed. Now saving adapter...")
            self.model.save_pretrained(output_dir)
            self.tokenizer.save_pretrained(output_dir)
            
            logger.info("LoRA adapter saved successfully.")
            return True
        except Exception as e:
            logger.error(f"An error occurred during training or saving: {e}", exc_info=True)
            return False

class NarrativeDbDataset(Dataset):
    """Lädt Dialog-Paare aus der Datenbank und bereitet sie für das Training vor."""
    def __init__(self, data: List[Dict[str, str]], tokenizer: Any, max_length: int):
        self.data = data
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        # Formatiert den Dialog im einfachen Frage-Antwort-Stil
        item = self.data[idx]
        tokenized_item = self.tokenizer(
            item['text'],
            truncation=True,
            max_length=self.max_length,
            padding="max_length"
        )
        return {"input_ids": torch.tensor(tokenized_item["input_ids"]),
                "attention_mask": torch.tensor(tokenized_item["attention_mask"]),
                "labels": torch.tensor(tokenized_item["input_ids"])}