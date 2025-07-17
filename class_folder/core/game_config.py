# class/game_config.py
# -*- coding: utf-8 -*-

"""
Central configuration values for the 'Last-Strawberry' AI Text Adventure.
"""

import torch

# --- Core AI Model Configuration ---
# We are using Meta's Llama 3 8B Instruct model as the foundation.
# It's highly capable in creative writing and following instructions.
HF_BASE_MODEL_NAME = "meta-llama/Meta-Llama-3-8B-Instruct"


# --- Database Configuration ---
# For Phase 1 (Solo Adventure), we use a simple local SQLite database.
DATABASE_PATH = "laststrawberry.db"


# --- Technical Settings ---
# These settings are similar to the Signz-Mind project and will be used
# for the training and inference pipeline.
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# QLoRA / bitsandbytes configuration for fine-tuning
BNB_LOAD_IN_4BIT = True
BNB_4BIT_QUANT_TYPE = "nf4"
BNB_4BIT_COMPUTE_DTYPE = torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float16
BNB_4BIT_USE_DOUBLE_QUANT = True

# LoRA configuration
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
# Note: Target modules might need to be adjusted for Llama 3
LORA_TARGET_MODULES = ["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
LORA_TASK_TYPE = "CAUSAL_LM"

