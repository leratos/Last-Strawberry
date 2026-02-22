export const GAME_API_BASE_URL =
  import.meta.env.VITE_GAME_API_BASE_URL?.toString() || "http://127.0.0.1:8010";

type JsonObject = Record<string, unknown>;

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
  recent_turns: Array<{
    turn_id: string;
    raw_player_input: string;
    narrative: { narrative: string };
    resolution: {
      system_events: Array<{ code: string; message: string; severity: string }>;
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
  retrieval_player_input: string | null;
  retrieval_notes: string[];
};

export type WorldBootstrapRequest = {
  user_id: string;
  world_description: string;
  character_description: string;
  tone?: string;
  difficulty?: string;
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

export async function createWorldBootstrap(payload: WorldBootstrapRequest): Promise<{ world_id: string }> {
  return apiFetch<{ world_id: string }>("/v1/worlds/bootstrap", {
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

export async function runTurn(worldId: string, playerInput: string): Promise<JsonObject> {
  return apiFetch<JsonObject>(`/v1/worlds/${worldId}/turns/run`, {
    method: "POST",
    body: JSON.stringify({ player_input: playerInput }),
  });
}
