export const GAME_API_BASE_URL =
  import.meta.env.VITE_GAME_API_BASE_URL?.toString() || "http://127.0.0.1:8010";

export type GameContextResponse = {
  world: {
    world_id: string;
    initial_narrative: string;
    world_seed: {
      name: string;
      start_location_name: string;
      summary: string;
    };
    character_state: {
      world_character_id: string;
      name: string;
      location_name: string;
      scene_zone_id: string;
      scene_zone_name: string;
      level: number;
      xp: number;
      resources: {
        hp: number;
        max_hp: number;
        stamina: number;
        max_stamina: number;
        focus: number;
        max_focus: number;
      };
      attributes: Record<string, number>;
      status_effects: string[];
    };
    inventory: Array<{
      inventory_item_id: string;
      name: string;
      quantity: number;
      use_modes: string[];
    }>;
    journal: Array<{
      journal_entry_id: string;
      entry_type: string;
      text: string;
      created_at: string;
    }>;
  };
  world_pack?: {
    pack_id: string;
    version: string;
    display_name: string;
    genre: string;
  };
  story_flags?: Record<string, string | number | boolean>;
  quests: Array<{
    quest_id: string;
    title: string;
    description: string;
    status: string;
    current_stage: string;
    objectives: Array<{
      objective_id: string;
      title: string;
      status: string;
      hint: string;
    }>;
    tags: string[];
    updated_at: string;
    completed_at?: string | null;
  }>;
  recent_turns: Array<{
    turn_id: string;
    raw_player_input: string;
    narrative: { narrative: string };
    resolution: {
      system_events: Array<{
        code: string;
        message: string;
        severity: string;
        metadata?: Record<string, string | number | boolean | null>;
        clarify?: {
          reason?: string | null;
          suggested_action?: string | null;
          candidates: Array<{
            action_type: string;
            target_ref: string;
            target_kind?: string | null;
            label?: string | null;
            name?: string | null;
            role?: string | null;
            kind?: string | null;
            faction?: string | null;
            location_name?: string | null;
            scene_zone_name?: string | null;
            distance_band_to_player?: string | null;
          }>;
        } | null;
      }>;
    };
  }>;
  recent_journal: Array<{
    journal_entry_id: string;
    entry_type: string;
    text: string;
    created_at: string;
  }>;
  npc_memory: Array<{
    relevance_score: number;
    retrieval_reasons: string[];
    bundle: {
      profile: {
        npc_id: string;
        name: string;
        role: string;
        faction?: string | null;
        location_name?: string | null;
        scene_zone_id?: string | null;
        scene_zone_name?: string | null;
      };
      relationship: null | {
        standing: number;
        tags: string[];
        notes: string;
      };
      recent_memories: Array<{
        memory_id: string;
        summary: string;
        importance: number;
        tags: string[];
      }>;
    };
  }>;
  target_catalog: {
    npcs: Array<{
      ref_id: string;
      kind: string;
      name: string;
      role?: string | null;
      faction?: string | null;
      source: string;
      location_name?: string | null;
      scene_zone_id?: string | null;
      scene_zone_name?: string | null;
      distance_band_to_player?: string | null;
      detail_level?: number | null;
      discovery_state?: Record<string, string | number | boolean | null>;
    }>;
    items: Array<{
      ref_id: string;
      kind: string;
      name: string;
      source: string;
      location_name?: string | null;
      scene_zone_id?: string | null;
      scene_zone_name?: string | null;
      distance_band_to_player?: string | null;
      detail_level?: number | null;
      discovery_state?: Record<string, string | number | boolean | null>;
    }>;
    locations: Array<{
      ref_id: string;
      kind: string;
      name: string;
      source: string;
      location_name?: string | null;
      scene_zone_id?: string | null;
      scene_zone_name?: string | null;
      distance_band_to_player?: string | null;
      detail_level?: number | null;
      discovery_state?: Record<string, string | number | boolean | null>;
    }>;
    scene_points: Array<{
      ref_id: string;
      kind: string;
      name: string;
      source: string;
      aliases?: string[];
      location_name?: string | null;
      scene_zone_id?: string | null;
      scene_zone_name?: string | null;
      distance_band_to_player?: string | null;
      detail_level?: number | null;
      discovery_state?: Record<string, string | number | boolean | null>;
    }>;
  };
  retrieval_player_input: string | null;
  retrieval_notes: string[];
  discovery_counts?: {
    hidden_npc_count?: number;
    hidden_scene_point_count?: number;
    visible_scene_point_count?: number;
    detail_verified_scene_point_count?: number;
  };
};

export type LlmCapabilityTraceView = {
  capability: string;
  mode: string;
  provider_policy: string;
  provider_used: string;
  model?: string | null;
  fallback_used: boolean;
  fallback_reason?: string | null;
};

export type TurnRunResponse = {
  turn: {
    turn_id: string;
  };
  journal_entry_ids: string[];
  analysis_context_notes: string[];
  provider_trace?: {
    intent: LlmCapabilityTraceView;
    narration: LlmCapabilityTraceView;
  } | null;
  context_before_turn: GameContextResponse | null;
  context_after_turn: GameContextResponse | null;
};

export type StructuredTurnAction = {
  action_type: "MOVE" | "APPROACH" | "RETREAT" | "TALK" | "ATTACK" | "USE_ITEM" | "INSPECT" | "OPEN" | "SEARCH" | "TAKE";
  target_ref?: string | null;
  destination?: string | null;
  item_ref?: string | null;
  target_kind?: string | null;
  parameters?: Record<string, string | number | boolean | null>;
  confidence?: number;
};

export type WorldBootstrapRequest = {
  user_id: string;
  world_description: string;
  character_description: string;
  tone?: string;
  difficulty?: string;
};

export type WorldBootstrapCreateResponse = {
  world_id: string;
  bootstrap_trace?: LlmCapabilityTraceView | null;
};

export type QuestAuthoringValidateResponse = {
  ok: boolean;
  spec_count: number;
  error_count: number;
  errors: string[];
};

export type QuestAuthoringDryRunResponse = {
  ok: boolean;
  world_id: string;
  validated_at_utc: string;
  spec_count: number;
  validation: {
    ok: boolean;
    error_count: number;
    errors: string[];
  };
  world_context: {
    quest_count: number;
    quest_ids: string[];
    story_flag_count: number;
    story_flags: Record<string, string | number | boolean>;
  };
  compiled_preview: {
    quest_count: number;
    quests: Array<Record<string, unknown>>;
  };
  diff: {
    quests_added: string[];
    flags_changed: Array<Record<string, string | null>>;
    objectives_changed: Array<Record<string, string>>;
    events_expected: Array<Record<string, string | null>>;
  };
};

export type QuestAuthoringApplyResponse = {
  ok: boolean;
  world_id: string;
  audit_id: string;
  applied_count: number;
  applied_quest_ids: string[];
  world_character_id: string;
};

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${GAME_API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text}`);
  }

  return (await response.json()) as T;
}

export async function createWorldBootstrap(payload: WorldBootstrapRequest): Promise<WorldBootstrapCreateResponse> {
  return apiFetch<WorldBootstrapCreateResponse>("/v1/worlds/bootstrap", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getWorldContext(worldId: string, playerInputHint?: string): Promise<GameContextResponse> {
  const url = new URL(`/v1/worlds/${worldId}/context`, GAME_API_BASE_URL);
  if (playerInputHint && playerInputHint.trim()) {
    url.searchParams.set("player_input", playerInputHint.trim());
  }
  const response = await fetch(url.toString());
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text}`);
  }
  return (await response.json()) as GameContextResponse;
}

export async function runTurn(
  worldId: string,
  playerInput: string,
  options?: { actionsOverride?: StructuredTurnAction[] },
): Promise<TurnRunResponse> {
  return apiFetch<TurnRunResponse>(`/v1/worlds/${worldId}/turns/run`, {
    method: "POST",
    body: JSON.stringify({
      player_input: playerInput,
      include_context_after_turn: true,
      actions_override: options?.actionsOverride || [],
    }),
  });
}

export async function validateQuestSpecs(payload: {
  specs: Array<Record<string, unknown>>;
  existing_quest_ids?: string[];
}): Promise<QuestAuthoringValidateResponse> {
  return apiFetch<QuestAuthoringValidateResponse>("/v1/quest-specs/validate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function dryRunQuestSpecs(payload: {
  world_id: string;
  specs: Array<Record<string, unknown>>;
  existing_quest_ids?: string[];
}): Promise<QuestAuthoringDryRunResponse> {
  return apiFetch<QuestAuthoringDryRunResponse>("/v1/quest-specs/preview/dry-run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function applyQuestSpecs(payload: {
  world_id: string;
  specs: Array<Record<string, unknown>>;
  existing_quest_ids?: string[];
  requested_by?: string;
  source?: string;
}): Promise<QuestAuthoringApplyResponse> {
  return apiFetch<QuestAuthoringApplyResponse>("/v1/quest-specs/apply", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
