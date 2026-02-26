import { FormEvent, useMemo, useState } from "react";
import {
  createWorldBootstrap,
  GAME_API_BASE_URL,
  GameContextResponse,
  getWorldContext,
  LlmCapabilityTraceView,
  runTurn,
  StructuredTurnAction,
  TurnRunResponse,
} from "./api";

type BootstrapForm = {
  userId: string;
  worldDescription: string;
  characterDescription: string;
};

type StructuredActionKind = "MOVE" | "APPROACH" | "RETREAT" | "TALK" | "ATTACK" | "USE_ITEM";
type StructuredTarget = {
  refId: string;
  name: string;
  kind: string;
  role?: string;
  auxiliary?: string;
  locationName?: string;
  sceneZoneId?: string;
  sceneZoneName?: string;
  distanceBandToPlayer?: string;
  standing?: number;
};
type QueuedStructuredAction = {
  label: string;
  action: StructuredTurnAction;
};
type QueueMacro = {
  name: string;
  entries: QueuedStructuredAction[];
};
type ClarifyCandidate = {
  action_type: "TALK" | "INSPECT" | "OPEN" | "SEARCH" | "TAKE";
  target_ref: string;
  target_kind?: string;
  label?: string;
  name?: string;
  role?: string;
  kind?: string;
  faction?: string;
  location_name?: string;
  scene_zone_name?: string;
  distance_band_to_player?: string;
};
type DialogTopicOption = {
  topic_id: string;
  label: string;
  summary?: string;
  future_check_attribute?: string;
  future_check_label?: string;
  future_check_dc?: number;
  requires_flag?: string;
  followup_of?: string;
  followup_condition?: string;
  effect_hint?: string;
  dialog_tree_group?: string;
  dialog_tree_step?: number;
};
type TurnSystemEventView = GameContextResponse["recent_turns"][number]["resolution"]["system_events"][number];
type TurnEventMetadata = NonNullable<TurnSystemEventView["metadata"]>;
type ActiveClarifyState = {
  turnId: string;
  rawPlayerInput: string;
  event: TurnSystemEventView;
};
type TurnProviderTraceView = NonNullable<TurnRunResponse["provider_trace"]>;
type DistanceBand = "adjacent" | "near" | "far" | "unreachable" | string | undefined | null;
type ScenePointFilter = "all" | "container" | "scene_object" | "scene_point" | "unknown";
type ScenePointSort = "name" | "detail" | "zone";

const QUEUE_MACROS_STORAGE_KEY = "ls_web_queue_macros_v1";

const DEFAULT_BOOTSTRAP: BootstrapForm = {
  userId: "local-dev-user",
  worldDescription:
    "Eine sturmgepeitschte Hafenstadt mit Schmugglern, Nachtmaerkten und rivalisierenden Fraktionen.",
  characterDescription:
    "Eine ehemalige Kartografin, die ihre verschollene Schwester sucht und dafuer mit Informationen handelt.",
};

function loadQueueMacrosFromStorage(): QueueMacro[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(QUEUE_MACROS_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .filter((entry) => entry && typeof entry === "object")
      .map((entry) => {
        const candidate = entry as { name?: unknown; entries?: unknown };
        const name = typeof candidate.name === "string" ? candidate.name.trim().slice(0, 80) : "";
        const entries = Array.isArray(candidate.entries) ? (candidate.entries as QueuedStructuredAction[]) : [];
        return { name, entries };
      })
      .filter((entry) => entry.name && entry.entries.length > 0);
  } catch {
    return [];
  }
}

function saveQueueMacrosToStorage(macros: QueueMacro[]): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(QUEUE_MACROS_STORAGE_KEY, JSON.stringify(macros));
}

function parseDialogTopicOptions(rawValue: unknown): DialogTopicOption[] {
  if (typeof rawValue !== "string" || !rawValue.trim()) {
    return [];
  }
  try {
    const parsed = JSON.parse(rawValue) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .filter((entry) => entry && typeof entry === "object")
      .map((entry) => {
        const topic = entry as {
          topic_id?: unknown;
          label?: unknown;
          summary?: unknown;
          future_check_attribute?: unknown;
          future_check_label?: unknown;
          future_check_dc?: unknown;
          requires_flag?: unknown;
          followup_of?: unknown;
          followup_condition?: unknown;
          effect_hint?: unknown;
          dialog_tree_group?: unknown;
          dialog_tree_step?: unknown;
        };
        return {
          topic_id: typeof topic.topic_id === "string" ? topic.topic_id.trim() : "",
          label: typeof topic.label === "string" ? topic.label.trim() : "",
          summary: typeof topic.summary === "string" ? topic.summary.trim() : undefined,
          future_check_attribute:
            typeof topic.future_check_attribute === "string" ? topic.future_check_attribute.trim() : undefined,
          future_check_label: typeof topic.future_check_label === "string" ? topic.future_check_label.trim() : undefined,
          future_check_dc:
            typeof topic.future_check_dc === "number"
              ? topic.future_check_dc
              : typeof topic.future_check_dc === "string" && topic.future_check_dc.trim()
                ? Number(topic.future_check_dc)
                : undefined,
          requires_flag: typeof topic.requires_flag === "string" ? topic.requires_flag.trim() : undefined,
          followup_of: typeof topic.followup_of === "string" ? topic.followup_of.trim() : undefined,
          followup_condition: typeof topic.followup_condition === "string" ? topic.followup_condition.trim() : undefined,
          effect_hint: typeof topic.effect_hint === "string" ? topic.effect_hint.trim() : undefined,
          dialog_tree_group: typeof topic.dialog_tree_group === "string" ? topic.dialog_tree_group.trim() : undefined,
          dialog_tree_step:
            typeof topic.dialog_tree_step === "number"
              ? topic.dialog_tree_step
              : typeof topic.dialog_tree_step === "string" && topic.dialog_tree_step.trim()
                ? Number(topic.dialog_tree_step)
                : undefined,
        };
      })
      .filter((topic) => Boolean(topic.topic_id && topic.label));
  } catch {
    return [];
  }
}

function isApproachNotNeeded(distanceBand: DistanceBand): boolean {
  return (distanceBand || "").toString().toLowerCase() === "adjacent";
}

function isRetreatNotNeeded(distanceBand: DistanceBand): boolean {
  const normalized = (distanceBand || "").toString().toLowerCase();
  return normalized === "far" || normalized === "unreachable";
}

function distanceBandDisplayLabel(distanceBand: DistanceBand): string {
  const normalized = (distanceBand || "").toString().toLowerCase();
  if (!normalized) {
    return "?";
  }
  if (normalized === "adjacent") {
    return "adjacent (direkt)";
  }
  if (normalized === "near") {
    return "near (nah)";
  }
  if (normalized === "far") {
    return "far (weit)";
  }
  if (normalized === "unreachable") {
    return "unreachable";
  }
  return normalized;
}

function distanceActionHint(distanceBand: DistanceBand): string {
  const normalized = (distanceBand || "").toString().toLowerCase();
  if (!normalized) {
    return "Distanz unbekannt: Annaehern/Abstand moeglich, Ergebnis haengt vom Kontext ab.";
  }
  if (normalized === "adjacent") {
    return "Direkt daneben: Annaehern nicht noetig, Abstand sinnvoll.";
  }
  if (normalized === "near") {
    return "Nah dran: Sowohl Annaehern als auch Abstand moeglich.";
  }
  if (normalized === "far") {
    return "Bereits weit entfernt: Abstand bringt nichts mehr, Annaehern sinnvoll.";
  }
  if (normalized === "unreachable") {
    return "Ziel derzeit nicht erreichbar: Abstand nicht relevant, ggf. Ort wechseln.";
  }
  return `Distanz: ${normalized}`;
}

function approachButtonLabel(distanceBand: DistanceBand): string {
  return isApproachNotNeeded(distanceBand) ? "Annaehern (direkt dran)" : "Annaehern";
}

function retreatButtonLabel(distanceBand: DistanceBand): string {
  return isRetreatNotNeeded(distanceBand) ? "Abstand (max)" : "Abstand";
}

function reactionStyleKey(role: string | undefined, standing: number | undefined): "freundlich" | "vorsichtig" | "aggressiv" {
  const normalizedRole = (role || "").trim().toLowerCase();
  const aggressiveRoles = new Set(["guard", "soldier", "mercenary", "bandit", "raider", "thug", "warrior", "krieger", "tank"]);
  const friendlyRoles = new Set(["healer", "heiler", "merchant", "haendler", "händler", "innkeeper", "guide", "ally"]);
  const arcaneRoles = new Set(["mage", "magier", "wizard", "sorcerer", "summoner", "beschwoerer", "beschwörer"]);
  const safeStanding = typeof standing === "number" ? standing : 0;

  if (safeStanding >= 3) {
    return "freundlich";
  }
  if (safeStanding <= -4) {
    return "aggressiv";
  }
  if (safeStanding <= -2 && aggressiveRoles.has(normalizedRole)) {
    return "aggressiv";
  }
  if (safeStanding <= 0) {
    return "vorsichtig";
  }
  if (arcaneRoles.has(normalizedRole) && safeStanding < 3) {
    return "vorsichtig";
  }
  if (friendlyRoles.has(normalizedRole)) {
    return "freundlich";
  }
  return "vorsichtig";
}

function reactionStyleLabel(role: string | undefined, standing: number | undefined): string {
  return `Reaktion: ${reactionStyleKey(role, standing)}`;
}

function reactionStyleBadgeClass(role: string | undefined, standing: number | undefined): string {
  const style = reactionStyleKey(role, standing);
  if (style === "aggressiv") {
    return "npc-badge-aggressiv";
  }
  if (style === "freundlich") {
    return "npc-badge-freundlich";
  }
  return "npc-badge-vorsichtig";
}

function formatCapabilityTraceSummary(trace: LlmCapabilityTraceView): string {
  const modelSuffix = trace.model ? ` (${trace.model})` : "";
  const fallbackSuffix = trace.fallback_used
    ? ` -> fallback${trace.fallback_reason ? `:${trace.fallback_reason}` : ""}`
    : "";
  return `${trace.capability}: ${trace.provider_used}${modelSuffix}${fallbackSuffix}`;
}

function eventGroupLabel(eventCode: string): string {
  if (eventCode.startsWith("npc_reacts_")) {
    return "Reaktion";
  }
  if (
    eventCode.includes("approach") ||
    eventCode.includes("retreat") ||
    eventCode.includes("move_")
  ) {
    return "Bewegung";
  }
  if (eventCode.includes("attack") || eventCode.includes("ranged_")) {
    return "Kampf";
  }
  if (eventCode.includes("talk")) {
    return "Dialog";
  }
  if (eventCode.includes("item_") || eventCode === "item_used") {
    return "Item";
  }
  return "System";
}

function eventGroupClass(eventCode: string): string {
  if (eventCode.startsWith("npc_reacts_")) {
    return "event-group-reaction";
  }
  if (
    eventCode.includes("approach") ||
    eventCode.includes("retreat") ||
    eventCode.includes("move_")
  ) {
    return "event-group-movement";
  }
  if (eventCode.includes("attack") || eventCode.includes("ranged_")) {
    return "event-group-combat";
  }
  if (eventCode.includes("talk")) {
    return "event-group-dialog";
  }
  return "event-group-system";
}

type SkillCheckEventSummary = {
  label: string;
  attribute: string;
  attributeScore: number;
  modifier: number;
  roll: number;
  total: number;
  dc: number;
  success: boolean;
};

function asMetadataNumber(metadata: TurnEventMetadata | undefined, key: string): number | null {
  const value = metadata?.[key];
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function asMetadataBoolean(metadata: TurnEventMetadata | undefined, key: string): boolean | null {
  const value = metadata?.[key];
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    if (value.toLowerCase() === "true") {
      return true;
    }
    if (value.toLowerCase() === "false") {
      return false;
    }
  }
  return null;
}

function getSkillCheckEventSummary(event: TurnSystemEventView): SkillCheckEventSummary | null {
  if (event.code !== "dialog_topic_skill_check") {
    return null;
  }
  const metadata = event.metadata;
  const label = typeof metadata?.check_label === "string" ? metadata.check_label : "";
  const attribute = typeof metadata?.check_attribute === "string" ? metadata.check_attribute : "";
  const attributeScore = asMetadataNumber(metadata, "attribute_score");
  const modifier = asMetadataNumber(metadata, "modifier");
  const roll = asMetadataNumber(metadata, "roll");
  const total = asMetadataNumber(metadata, "total");
  const dc = asMetadataNumber(metadata, "dc");
  const success = asMetadataBoolean(metadata, "success");
  if (
    !label ||
    !attribute ||
    attributeScore === null ||
    modifier === null ||
    roll === null ||
    total === null ||
    dc === null ||
    success === null
  ) {
    return null;
  }
  return {
    label,
    attribute,
    attributeScore,
    modifier,
    roll,
    total,
    dc,
    success,
  };
}

function formatSignedNumber(value: number): string {
  return `${value >= 0 ? "+" : "-"}${Math.abs(value)}`;
}

function parseClarifyCandidates(
  metadata: Record<string, string | number | boolean | null> | undefined,
): ClarifyCandidate[] {
  const raw = metadata?.candidates_json;
  if (typeof raw !== "string" || !raw.trim()) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .filter((entry) => entry && typeof entry === "object")
      .map((entry) => {
        const candidate = entry as Record<string, unknown>;
        return {
          action_type: String(candidate.action_type || "").toUpperCase() as ClarifyCandidate["action_type"],
          target_ref: String(candidate.target_ref || ""),
          target_kind: candidate.target_kind ? String(candidate.target_kind) : undefined,
          label: candidate.label ? String(candidate.label) : undefined,
          name: candidate.name ? String(candidate.name) : undefined,
          role: candidate.role ? String(candidate.role) : undefined,
          kind: candidate.kind ? String(candidate.kind) : undefined,
          faction: candidate.faction ? String(candidate.faction) : undefined,
          location_name: candidate.location_name ? String(candidate.location_name) : undefined,
          scene_zone_name: candidate.scene_zone_name ? String(candidate.scene_zone_name) : undefined,
          distance_band_to_player: candidate.distance_band_to_player ? String(candidate.distance_band_to_player) : undefined,
        };
      })
      .filter((entry) => entry.action_type && entry.target_ref);
  } catch {
    return [];
  }
}

function normalizeClarifyCandidates(
  event: {
    metadata?: Record<string, string | number | boolean | null>;
    clarify?: { candidates?: Array<Record<string, unknown>> | null } | null;
  },
): ClarifyCandidate[] {
  const structured = event.clarify?.candidates;
  if (Array.isArray(structured) && structured.length > 0) {
    return structured
      .map((candidate) => ({
        action_type: String(candidate.action_type || "").toUpperCase() as ClarifyCandidate["action_type"],
        target_ref: String(candidate.target_ref || ""),
        target_kind: candidate.target_kind ? String(candidate.target_kind) : undefined,
        label: candidate.label ? String(candidate.label) : undefined,
        name: candidate.name ? String(candidate.name) : undefined,
        role: candidate.role ? String(candidate.role) : undefined,
        kind: candidate.kind ? String(candidate.kind) : undefined,
        faction: candidate.faction ? String(candidate.faction) : undefined,
        location_name: candidate.location_name ? String(candidate.location_name) : undefined,
        scene_zone_name: candidate.scene_zone_name ? String(candidate.scene_zone_name) : undefined,
        distance_band_to_player: candidate.distance_band_to_player ? String(candidate.distance_band_to_player) : undefined,
      }))
      .filter((entry) => entry.action_type && entry.target_ref);
  }
  return parseClarifyCandidates(event.metadata);
}

function clarifyReasonValue(
  event: {
    metadata?: Record<string, string | number | boolean | null>;
    clarify?: { reason?: string | null } | null;
  },
): string {
  if (typeof event.clarify?.reason === "string" && event.clarify.reason.trim()) {
    return event.clarify.reason;
  }
  if (typeof event.metadata?.reason === "string" && event.metadata.reason.trim()) {
    return event.metadata.reason;
  }
  return "";
}

function clarifySuggestedActionValue(
  event: {
    metadata?: Record<string, string | number | boolean | null>;
    clarify?: { suggested_action?: string | null } | null;
  },
): string {
  if (typeof event.clarify?.suggested_action === "string" && event.clarify.suggested_action.trim()) {
    return event.clarify.suggested_action;
  }
  if (typeof event.metadata?.suggested_action === "string" && event.metadata.suggested_action.trim()) {
    return event.metadata.suggested_action;
  }
  return "";
}

function findLatestClarifyState(context: GameContextResponse | null): ActiveClarifyState | null {
  if (!context) {
    return null;
  }
  const latestTurn = context.recent_turns[context.recent_turns.length - 1];
  if (!latestTurn) {
    return null;
  }
  const clarifyEvent = latestTurn.resolution.system_events.find((event) => event.code === "clarify_required");
  if (!clarifyEvent) {
    return null;
  }
  return {
    turnId: latestTurn.turn_id,
    rawPlayerInput: latestTurn.raw_player_input,
    event: clarifyEvent,
  };
}

function structuredActionKindFromClarifyCandidate(candidate: ClarifyCandidate): StructuredActionKind | null {
  const actionType = (candidate.action_type || "").toUpperCase();
  if (actionType === "TALK") {
    return "TALK";
  }
  return null;
}

function clarifyReasonLabel(reason?: string | null): string {
  const normalized = (reason || "").trim().toLowerCase();
  if (!normalized) {
    return "Rueckfrage";
  }
  if (normalized.includes("ambiguous") || normalized.includes("mehrdeutig")) {
    return "Mehrdeutig";
  }
  if (normalized.includes("unknown") || normalized.includes("unbekannt")) {
    return "Unbekannt";
  }
  return normalized.replace(/_/g, " ");
}

function clarifyCandidateGroupLabel(candidate: ClarifyCandidate): string {
  const kind = (candidate.target_kind || candidate.kind || "").toLowerCase();
  if (kind === "npc") {
    return "NPCs";
  }
  if (kind === "container") {
    return "Container";
  }
  if (kind === "scene_object") {
    return "Objekte";
  }
  if (kind === "scene_point") {
    return "Interaktionspunkte";
  }
  return "Ziele";
}

function groupClarifyCandidates(candidates: ClarifyCandidate[]): Array<{ label: string; items: ClarifyCandidate[] }> {
  const grouped = new Map<string, ClarifyCandidate[]>();
  for (const candidate of candidates) {
    const group = clarifyCandidateGroupLabel(candidate);
    grouped.set(group, [...(grouped.get(group) || []), candidate]);
  }
  return Array.from(grouped.entries()).map(([label, items]) => ({ label, items }));
}

function clarifyCandidateSubtitle(candidate: ClarifyCandidate): string {
  const parts: string[] = [];
  if (candidate.role) {
    parts.push(`Rolle: ${candidate.role}`);
  }
  if (candidate.kind && candidate.kind !== candidate.target_kind) {
    parts.push(`Typ: ${candidate.kind}`);
  } else if (candidate.target_kind && candidate.target_kind !== "npc") {
    parts.push(`Typ: ${candidate.target_kind}`);
  }
  if (candidate.location_name || candidate.scene_zone_name) {
    parts.push(
      `Ort/Zone: ${candidate.location_name || "?"}${candidate.scene_zone_name ? ` / ${candidate.scene_zone_name}` : ""}`,
    );
  }
  if (candidate.distance_band_to_player) {
    parts.push(`Distanz: ${distanceBandDisplayLabel(candidate.distance_band_to_player)}`);
  }
  if (candidate.faction) {
    parts.push(`Fraktion: ${candidate.faction}`);
  }
  return parts.join(" | ");
}

function getStructuredTargets(
  context: GameContextResponse,
  composerActionKind: StructuredActionKind,
): StructuredTarget[] {
  if (composerActionKind === "MOVE") {
    return context.target_catalog.locations.map((entry) => ({
      refId: entry.ref_id,
      name: entry.name,
      kind: "location",
      locationName: entry.location_name || undefined,
      sceneZoneId: entry.scene_zone_id || undefined,
      sceneZoneName: entry.scene_zone_name || undefined,
      distanceBandToPlayer: entry.distance_band_to_player || undefined,
    }));
  }
  if (composerActionKind === "USE_ITEM") {
    return context.world.inventory.map((item) => ({
      refId: item.inventory_item_id,
      name: item.name,
      kind: "item",
      auxiliary: item.use_modes.join(", "),
    }));
  }
  if (composerActionKind === "APPROACH" || composerActionKind === "RETREAT") {
    return context.target_catalog.npcs.map((entry) => ({
      refId: entry.ref_id,
      name: entry.name,
      kind: "npc",
      role: entry.role || undefined,
      locationName: entry.location_name || undefined,
      sceneZoneId: entry.scene_zone_id || undefined,
      sceneZoneName: entry.scene_zone_name || undefined,
      distanceBandToPlayer: entry.distance_band_to_player || undefined,
    }));
  }
  return context.target_catalog.npcs.map((entry) => ({
    refId: entry.ref_id,
    name: entry.name,
    kind: "npc",
    role: entry.role || undefined,
    locationName: entry.location_name || undefined,
    sceneZoneId: entry.scene_zone_id || undefined,
    sceneZoneName: entry.scene_zone_name || undefined,
    distanceBandToPlayer: entry.distance_band_to_player || undefined,
  }));
}

export function App() {
  const [bootstrapForm, setBootstrapForm] = useState<BootstrapForm>(DEFAULT_BOOTSTRAP);
  const [worldId, setWorldId] = useState<string>("");
  const [worldIdInput, setWorldIdInput] = useState<string>("");
  const [turnInput, setTurnInput] = useState<string>("Ich spreche mit einem Haendler ueber Geruechte.");
  const [context, setContext] = useState<GameContextResponse | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(false);
  const [isRunningTurn, setIsRunningTurn] = useState(false);
  const [isReloading, setIsReloading] = useState(false);
  const [lastActionMessage, setLastActionMessage] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [analysisNotes, setAnalysisNotes] = useState<string[]>([]);
  const [lastProviderTrace, setLastProviderTrace] = useState<TurnProviderTraceView | null>(null);
  const [lastBootstrapTrace, setLastBootstrapTrace] = useState<LlmCapabilityTraceView | null>(null);
  const [composerActionKind, setComposerActionKind] = useState<StructuredActionKind>("TALK");
  const [composerAttackMode, setComposerAttackMode] = useState<"melee" | "ranged">("melee");
  const [composerTargetRef, setComposerTargetRef] = useState<string>("");
  const [structuredQueue, setStructuredQueue] = useState<QueuedStructuredAction[]>([]);
  const [queueMacros, setQueueMacros] = useState<QueueMacro[]>(() => loadQueueMacrosFromStorage());
  const [queueMacroName, setQueueMacroName] = useState<string>("");
  const [scenePointFilter, setScenePointFilter] = useState<ScenePointFilter>("all");
  const [scenePointSort, setScenePointSort] = useState<ScenePointSort>("name");

  const latestNarrative = useMemo(() => {
    if (!context) {
      return "";
    }
    const latestTurn = context.recent_turns[context.recent_turns.length - 1];
    return latestTurn?.narrative?.narrative || context.world.initial_narrative;
  }, [context]);

  const composerTargets = useMemo(() => {
    if (!context) {
      return [] as StructuredTarget[];
    }
    return getStructuredTargets(context, composerActionKind);
  }, [composerActionKind, context]);

  const selectedComposerTarget = useMemo(
    () => composerTargets.find((entry) => entry.refId === composerTargetRef) || composerTargets[0] || null,
    [composerTargetRef, composerTargets],
  );

  const composerDistanceActionBlockedReason = useMemo(() => {
    if (!selectedComposerTarget) {
      return "";
    }
    if (composerActionKind === "APPROACH" && isApproachNotNeeded(selectedComposerTarget.distanceBandToPlayer)) {
      return "Annaehern nicht noetig (bereits adjacent).";
    }
    if (composerActionKind === "RETREAT" && isRetreatNotNeeded(selectedComposerTarget.distanceBandToPlayer)) {
      return "Abstand nicht noetig (bereits far/unreachable).";
    }
    return "";
  }, [composerActionKind, selectedComposerTarget]);

  const activeClarify = useMemo(() => findLatestClarifyState(context), [context]);
  const providerTraceSummary = useMemo(() => {
    if (!lastProviderTrace) {
      return "";
    }
    return [lastProviderTrace.intent, lastProviderTrace.narration].map(formatCapabilityTraceSummary).join(" | ");
  }, [lastProviderTrace]);
  const bootstrapTraceSummary = useMemo(
    () => (lastBootstrapTrace ? formatCapabilityTraceSummary(lastBootstrapTrace) : ""),
    [lastBootstrapTrace],
  );
  const activeQuests = useMemo(
    () => (context?.quests || []).filter((quest) => (quest.status || "").toLowerCase() !== "completed"),
    [context],
  );
  const completedQuests = useMemo(
    () => (context?.quests || []).filter((quest) => (quest.status || "").toLowerCase() === "completed"),
    [context],
  );

  const scenePointsForDisplay = useMemo(() => {
    if (!context) {
      return [];
    }
    const filtered = context.target_catalog.scene_points.filter((point) => {
      if (scenePointFilter === "all") {
        return true;
      }
      if (scenePointFilter === "unknown") {
        return (point.detail_level || 1) < 2;
      }
      return point.kind === scenePointFilter;
    });
    const sorted = [...filtered];
    sorted.sort((a, b) => {
      if (scenePointSort === "detail") {
        return (b.detail_level || 1) - (a.detail_level || 1) || a.name.localeCompare(b.name);
      }
      if (scenePointSort === "zone") {
        return (a.scene_zone_name || "").localeCompare(b.scene_zone_name || "") || a.name.localeCompare(b.name);
      }
      return a.name.localeCompare(b.name);
    });
    return sorted;
  }, [context, scenePointFilter, scenePointSort]);

  async function loadContext(targetWorldId: string, retrievalHint?: string): Promise<void> {
    setIsReloading(true);
    setError("");
    try {
      const nextContext = await getWorldContext(targetWorldId, retrievalHint);
      setContext(nextContext);
      setWorldId(targetWorldId);
      setWorldIdInput(targetWorldId);
      if (!retrievalHint) {
        setLastProviderTrace(null);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Context konnte nicht geladen werden.");
    } finally {
      setIsReloading(false);
    }
  }

  async function handleLoadWorldById(): Promise<void> {
    if (!worldIdInput.trim()) {
      return;
    }
    setLastActionMessage("");
    setLastBootstrapTrace(null);
    await loadContext(worldIdInput.trim());
    setLastActionMessage(`Welt geladen: ${worldIdInput.trim()}`);
  }

  async function handleBootstrapSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsBootstrapping(true);
    setError("");
    setLastActionMessage("");
    setLastBootstrapTrace(null);
    try {
      const created = await createWorldBootstrap({
        user_id: bootstrapForm.userId.trim(),
        world_description: bootstrapForm.worldDescription.trim(),
        character_description: bootstrapForm.characterDescription.trim(),
      });
      await loadContext(created.world_id);
    setAnalysisNotes([]);
    setLastProviderTrace(null);
      setLastBootstrapTrace(created.bootstrap_trace || null);
      setLastActionMessage(`Neue Welt erstellt: ${created.world_id}`);
    } catch (bootstrapError) {
      setError(bootstrapError instanceof Error ? bootstrapError.message : "Bootstrap fehlgeschlagen.");
    } finally {
      setIsBootstrapping(false);
    }
  }

  async function handleTurnSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!worldId.trim() || !turnInput.trim()) {
      return;
    }
    setIsRunningTurn(true);
    setError("");
    setLastActionMessage("");
    try {
      const runResult: TurnRunResponse = await runTurn(worldId.trim(), turnInput.trim());
      await applyTurnResult(runResult, worldId.trim(), turnInput.trim());
    } catch (turnError) {
      setError(turnError instanceof Error ? turnError.message : "Turn fehlgeschlagen.");
    } finally {
      setIsRunningTurn(false);
    }
  }

  async function handleStructuredTurnSubmit(): Promise<void> {
    if (!context || !worldId.trim()) {
      return;
    }
    const selected = composerTargets.find((entry) => entry.refId === composerTargetRef) || composerTargets[0];
    if (!selected) {
      setError("Bitte ein Ziel fuer die strukturierte Aktion waehlen.");
      return;
    }

    const action = buildStructuredAction(composerActionKind, selected);
    const label = buildStructuredActionLabel(composerActionKind, selected);
    await executeStructuredActions([{ label, action }], `Struktur-Turn: ${label}`);
  }

  function enqueueStructuredAction(actionKind: StructuredActionKind, target: StructuredTarget): void {
    const action = buildStructuredAction(actionKind, target);
    const label = buildStructuredActionLabel(actionKind, target);
    setStructuredQueue((current) => [...current, { label, action }]);
    setLastActionMessage(`Zur Queue hinzugefuegt: ${label}`);
    setError("");
  }

  function removeQueuedAction(indexToRemove: number): void {
    setStructuredQueue((current) => current.filter((_, index) => index !== indexToRemove));
    setLastActionMessage(`Queue-Eintrag ${indexToRemove + 1} entfernt.`);
    setError("");
  }

  function moveQueuedAction(indexToMove: number, direction: -1 | 1): void {
    setStructuredQueue((current) => {
      const nextIndex = indexToMove + direction;
      if (indexToMove < 0 || indexToMove >= current.length || nextIndex < 0 || nextIndex >= current.length) {
        return current;
      }
      const clone = [...current];
      const [entry] = clone.splice(indexToMove, 1);
      clone.splice(nextIndex, 0, entry);
      return clone;
    });
    setLastActionMessage(`Queue-Reihenfolge aktualisiert.`);
    setError("");
  }

  function saveCurrentQueueAsMacro(): void {
    const trimmedName = queueMacroName.trim();
    if (!trimmedName) {
      setError("Bitte einen Makro-Namen eingeben.");
      return;
    }
    if (structuredQueue.length === 0) {
      setError("Queue ist leer.");
      return;
    }
    setQueueMacros((current) => {
      const next = [
        ...current.filter((macro) => macro.name.toLowerCase() !== trimmedName.toLowerCase()),
        { name: trimmedName, entries: structuredQueue },
      ].sort((a, b) => a.name.localeCompare(b.name));
      saveQueueMacrosToStorage(next);
      return next;
    });
    setLastActionMessage(`Queue-Makro gespeichert: ${trimmedName}`);
    setError("");
  }

  function loadQueueMacro(name: string): void {
    const macro = queueMacros.find((entry) => entry.name === name);
    if (!macro) {
      setError(`Queue-Makro nicht gefunden: ${name}`);
      return;
    }
    setStructuredQueue(macro.entries);
    setQueueMacroName(macro.name);
    setLastActionMessage(`Queue-Makro geladen: ${macro.name}`);
    setError("");
  }

  function deleteQueueMacro(name: string): void {
    setQueueMacros((current) => {
      const next = current.filter((entry) => entry.name !== name);
      saveQueueMacrosToStorage(next);
      return next;
    });
    setLastActionMessage(`Queue-Makro geloescht: ${name}`);
    setError("");
  }

  async function handleQueueSubmit(): Promise<void> {
    if (structuredQueue.length === 0) {
      setError("Queue ist leer.");
      return;
    }
    await executeStructuredActions(structuredQueue, `Queue (${structuredQueue.length} Aktionen)`);
    setStructuredQueue([]);
  }

  async function executeStructuredActions(
    queuedActions: QueuedStructuredAction[],
    messagePrefix: string,
  ): Promise<void> {
    if (!worldId.trim()) {
      return;
    }
    setIsRunningTurn(true);
    setError("");
    setLastActionMessage("");
    try {
      const label = queuedActions.map((entry) => entry.label).join(" | ").slice(0, 500);
      const runResult = await runTurn(worldId.trim(), label, {
        actionsOverride: queuedActions.map((entry) => entry.action),
      });
      await applyTurnResult(runResult, worldId.trim(), label);
      setLastActionMessage(`${messagePrefix} ausgefuehrt (${runResult.turn.turn_id}).`);
    } catch (turnError) {
      setError(turnError instanceof Error ? turnError.message : "Struktur-Turn fehlgeschlagen.");
    } finally {
      setIsRunningTurn(false);
    }
  }

  function adoptClarifyCandidateIntoComposer(candidate: ClarifyCandidate): void {
    if (!context) {
      return;
    }
    const composerKind = structuredActionKindFromClarifyCandidate(candidate);
    if (!composerKind) {
      setLastActionMessage("Dieser Rueckfrage-Kandidat kann nur direkt ausgefuehrt werden.");
      return;
    }
    const targets = getStructuredTargets(context, composerKind);
    const match = targets.find((entry) => entry.refId === candidate.target_ref);
    setComposerActionKind(composerKind);
    setComposerTargetRef(match?.refId || "");
    setLastActionMessage(`Rueckfrage-Ziel in Struktur-Aktion uebernommen: ${candidate.label || candidate.name || candidate.target_ref}`);
    setError("");
  }

  async function applyTurnResult(runResult: TurnRunResponse, fallbackWorldId: string, retrievalHint: string): Promise<void> {
    setAnalysisNotes(runResult.analysis_context_notes || []);
    setLastProviderTrace(runResult.provider_trace || null);
    if (runResult.context_after_turn) {
      setContext(runResult.context_after_turn);
      setWorldId(runResult.context_after_turn.world.world_id);
      setWorldIdInput(runResult.context_after_turn.world.world_id);
    } else {
      await loadContext(fallbackWorldId, retrievalHint);
    }
    if (runResult.context_after_turn && composerTargetRef) {
      const stillExists = getStructuredTargets(runResult.context_after_turn, composerActionKind).some(
        (entry) => entry.refId === composerTargetRef,
      );
      if (!stillExists) {
        setComposerTargetRef("");
      }
    }
    setLastActionMessage(`Turn ausgefuehrt (${runResult.turn.turn_id}) und Context aktualisiert.`);
  }

  function buildStructuredAction(
    actionKind: StructuredActionKind,
    target: StructuredTarget,
  ): StructuredTurnAction {
    if (actionKind === "MOVE") {
      return {
        action_type: "MOVE",
        target_ref: target.refId,
        destination: target.name,
        target_kind: "location",
        parameters: {
          intent: "move",
          destination_id: target.refId,
          destination_name: target.name,
        },
        confidence: 0.99,
      };
    }
    if (actionKind === "USE_ITEM") {
      return {
        action_type: "USE_ITEM",
        item_ref: target.refId,
        target_ref: target.name,
        target_kind: "item",
        parameters: {
          intent: "use_item",
          item_id: target.refId,
          item_name: target.name,
          target_name: target.name,
        },
        confidence: 0.99,
      };
    }
    if (actionKind === "APPROACH") {
      return {
        action_type: "APPROACH",
        target_ref: target.refId,
        target_kind: "npc",
        parameters: {
          intent: "approach",
          target_id: target.refId,
          target_name: target.name,
          target_role: target.role ?? null,
          target_standing: target.standing ?? null,
          target_location_name: target.locationName || null,
          target_zone_id: target.sceneZoneId || null,
          target_zone_name: target.sceneZoneName || null,
          target_distance_band: target.distanceBandToPlayer || null,
        },
        confidence: 0.99,
      };
    }
    if (actionKind === "RETREAT") {
      return {
        action_type: "RETREAT",
        target_ref: target.refId,
        target_kind: "npc",
        parameters: {
          intent: "retreat",
          target_id: target.refId,
          target_name: target.name,
          target_role: target.role ?? null,
          target_standing: target.standing ?? null,
          target_location_name: target.locationName || null,
          target_zone_id: target.sceneZoneId || null,
          target_zone_name: target.sceneZoneName || null,
          target_distance_band: target.distanceBandToPlayer || null,
        },
        confidence: 0.99,
      };
    }
    const attackMode = actionKind === "ATTACK" ? composerAttackMode : "melee";
    return {
      action_type: actionKind,
      target_ref: target.refId,
      target_kind: "npc",
        parameters: {
          intent: actionKind === "TALK" ? "talk" : "attack",
          attack_mode: actionKind === "ATTACK" ? attackMode : null,
          target_id: target.refId,
          target_name: target.name,
          target_role: target.role ?? null,
          target_standing: target.standing ?? null,
          target_location_name: target.locationName || null,
          target_zone_id: target.sceneZoneId || null,
          target_zone_name: target.sceneZoneName || null,
          target_distance_band: target.distanceBandToPlayer || null,
        },
        confidence: 0.99,
      };
  }

  function buildStructuredActionLabel(
    actionKind: StructuredActionKind,
    target: StructuredTarget,
  ): string {
    if (actionKind === "MOVE") {
      return `UI: Gehe zu ${target.name}`;
    }
    if (actionKind === "USE_ITEM") {
      return `UI: Benutze ${target.name}`;
    }
    if (actionKind === "APPROACH") {
      return `UI: Naehere dich ${target.name}`;
    }
    if (actionKind === "RETREAT") {
      return `UI: Gewinne Abstand zu ${target.name}`;
    }
    if (actionKind === "ATTACK") {
      return `UI: ${composerAttackMode === "ranged" ? "Fernkampf" : "Nahkampf"} gegen ${target.name}`;
    }
    return `UI: Spreche mit ${target.name}`;
  }

  function buildClarifyCandidateAction(candidate: ClarifyCandidate): StructuredTurnAction {
    const actionType = candidate.action_type;
    const targetName = candidate.name || candidate.label || candidate.target_ref;
    return {
      action_type: actionType,
      target_ref: candidate.target_ref,
      target_kind: candidate.target_kind || (actionType === "TALK" ? "npc" : "scene_point"),
      parameters: {
        intent: actionType.toLowerCase(),
        target_id: candidate.target_ref,
        target_name: targetName,
        target_kind: candidate.target_kind || candidate.kind || null,
        target_role: candidate.role || null,
        target_location_name: candidate.location_name || null,
        target_zone_name: candidate.scene_zone_name || null,
        target_distance_band: candidate.distance_band_to_player || null,
      },
      confidence: 0.99,
    };
  }

  function buildTalkTopicAction(target: StructuredTarget, topic: DialogTopicOption): StructuredTurnAction {
    const base = buildStructuredAction("TALK", target);
    return {
      ...base,
      parameters: {
        ...(base.parameters || {}),
        topic_id: topic.topic_id,
        topic_label: topic.label,
      },
    };
  }

  async function runBroadInspectQuickAction(): Promise<void> {
    if (!worldId.trim()) {
      return;
    }
    await executeStructuredActions(
      [
        {
          label: "UI: Schau dich um",
          action: {
            action_type: "INSPECT",
            target_kind: "environment",
            parameters: { intent: "inspect" },
            confidence: 0.99,
          },
        },
      ],
      "Quick Action",
    );
  }

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div>
          <p className="eyebrow">Last Strawberry / G4</p>
          <h1>Web-Spiel MVP (Greenfield)</h1>
          <p className="subtitle">API: {GAME_API_BASE_URL}</p>
        </div>
        <div className="header-actions">
          <label className="compact-label">
            Welt-ID
            <input
              className="compact-input"
              value={worldIdInput}
              onChange={(event) => setWorldIdInput(event.target.value)}
              placeholder="world-..."
            />
          </label>
          <button className="secondary-btn" type="button" onClick={() => void handleLoadWorldById()}>
            Welt laden
          </button>
          <div className="chip">{context ? `World: ${context.world.world_id}` : "Kein aktiver Run"}</div>
        </div>
      </header>

      <section className="grid">
        <article className="panel panel-large">
          <div className="panel-header">
            <h2>Spielansicht / Turn-Loop</h2>
            <button
              type="button"
              className="secondary-btn"
              onClick={() => (worldId ? void loadContext(worldId) : undefined)}
              disabled={!worldId || isReloading}
            >
              {isReloading ? "Lade..." : "Context neu laden"}
            </button>
          </div>

          {!context ? (
            <form className="stack-form" onSubmit={handleBootstrapSubmit}>
              <label>
                User ID
                <input
                  value={bootstrapForm.userId}
                  onChange={(event) =>
                    setBootstrapForm((current) => ({ ...current, userId: event.target.value }))
                  }
                />
              </label>
              <label>
                Weltbeschreibung
                <textarea
                  rows={4}
                  value={bootstrapForm.worldDescription}
                  onChange={(event) =>
                    setBootstrapForm((current) => ({ ...current, worldDescription: event.target.value }))
                  }
                />
              </label>
              <label>
                Charakterbeschreibung
                <textarea
                  rows={4}
                  value={bootstrapForm.characterDescription}
                  onChange={(event) =>
                    setBootstrapForm((current) => ({ ...current, characterDescription: event.target.value }))
                  }
                />
              </label>
              <button className="primary-btn" type="submit" disabled={isBootstrapping}>
                {isBootstrapping ? "Erzeuge Welt..." : "Neue Welt starten"}
              </button>
            </form>
          ) : (
            <>
              <section className="story-panel">
                <div className="story-meta">
                  <span>{context.world.world_seed.name}</span>
                  {context.world_pack?.display_name ? <span>Pack: {context.world_pack.display_name}</span> : null}
                  <span>Ort: {context.world.character_state.location_name}</span>
                  <span>Zone: {context.world.character_state.scene_zone_name}</span>
                  <span>Turns: {context.recent_turns.length}</span>
                  <span>Refs: {context.target_catalog.npcs.length}/{context.target_catalog.items.length}/{context.target_catalog.locations.length}</span>
                </div>
                <p className="story-text">{latestNarrative}</p>
                {analysisNotes.length > 0 ? (
                  <p className="list-subtle analysis-notes">
                    Analyse-Kontext: {analysisNotes.join(" | ")}
                  </p>
                ) : null}
                {providerTraceSummary ? (
                  <p className="list-subtle analysis-notes">Provider-Trace: {providerTraceSummary}</p>
                ) : null}
                {bootstrapTraceSummary ? (
                  <p className="list-subtle analysis-notes">Bootstrap-Trace: {bootstrapTraceSummary}</p>
                ) : null}
                {context.quests.length > 0 ? (
                  <div className="npc-badge-row">
                    <span className="npc-badge npc-badge-distance">Quests aktiv: {activeQuests.length}</span>
                    <span className="npc-badge npc-badge-vorsichtig">Quests erledigt: {completedQuests.length}</span>
                  </div>
                ) : null}
                {(context.discovery_counts?.hidden_npc_count || 0) > 0 ||
                (context.discovery_counts?.hidden_scene_point_count || 0) > 0 ? (
                  <div className="npc-badge-row">
                    {(context.discovery_counts?.hidden_npc_count || 0) > 0 ? (
                      <span className="npc-badge npc-badge-vorsichtig">
                        Verborgene NPCs: {context.discovery_counts?.hidden_npc_count || 0}
                      </span>
                    ) : null}
                    {(context.discovery_counts?.hidden_scene_point_count || 0) > 0 ? (
                      <span className="npc-badge npc-badge-distance">
                        Unentdeckte Punkte/Objekte: {context.discovery_counts?.hidden_scene_point_count || 0}
                      </span>
                    ) : null}
                    <button
                      type="button"
                      className="secondary-btn"
                      disabled={isRunningTurn}
                      onClick={() => void runBroadInspectQuickAction()}
                    >
                      Umsehen
                    </button>
                  </div>
                ) : null}
              </section>

              {activeClarify ? (
                <section className="subpanel clarify-panel">
                  <div className="panel-header">
                    <h3>Rueckfrage aktiv</h3>
                    <span className="chip">Turn: {activeClarify.turnId}</span>
                  </div>
                  <p className="list-subtle">
                    Eingabe: {activeClarify.rawPlayerInput}
                  </p>
                  <div className="npc-badge-row">
                    <span className="npc-badge npc-badge-vorsichtig">
                      {clarifyReasonLabel(clarifyReasonValue(activeClarify.event))}
                    </span>
                    {clarifySuggestedActionValue(activeClarify.event) ? (
                      <span className="npc-badge npc-badge-distance">
                        Vorschlag: {clarifySuggestedActionValue(activeClarify.event)}
                      </span>
                    ) : null}
                  </div>
                  <p className="list-subtle">{activeClarify.event.message}</p>

                  {clarifySuggestedActionValue(activeClarify.event) === "inspect_broad" ? (
                    <div className="turn-actions">
                      <button
                        type="button"
                        className="secondary-btn"
                        disabled={isRunningTurn}
                        onClick={() => void runBroadInspectQuickAction()}
                      >
                        Umsehen (Rueckfrage loesen)
                      </button>
                    </div>
                  ) : null}

                  {groupClarifyCandidates(normalizeClarifyCandidates(activeClarify.event)).length > 0 ? (
                    <div className="clarify-groups">
                      {groupClarifyCandidates(normalizeClarifyCandidates(activeClarify.event)).map((group) => (
                        <div key={`active-clarify-${group.label}`} className="clarify-group-card">
                          <p className="list-title">{group.label} ({group.items.length})</p>
                          <div className="clarify-candidate-list">
                            {group.items.map((candidate, candidateIndex) => {
                              const subtitle = clarifyCandidateSubtitle(candidate);
                              const canAdoptToComposer = Boolean(structuredActionKindFromClarifyCandidate(candidate));
                              return (
                                <div
                                  key={`active-clarify-${group.label}-${candidate.target_ref}-${candidateIndex}`}
                                  className="clarify-candidate-row"
                                >
                                  <div>
                                    <p className="list-title">{candidate.label || candidate.name || candidate.target_ref}</p>
                                    {subtitle ? <p className="list-subtle">{subtitle}</p> : null}
                                  </div>
                                  <div className="turn-actions">
                                    <button
                                      type="button"
                                      className="secondary-btn"
                                      disabled={isRunningTurn}
                                      onClick={() =>
                                        void executeStructuredActions(
                                          [
                                            {
                                              label: `Clarify: ${candidate.label || candidate.name || candidate.target_ref}`,
                                              action: buildClarifyCandidateAction(candidate),
                                            },
                                          ],
                                          "Quick Action",
                                        )
                                      }
                                    >
                                      Ausfuehren
                                    </button>
                                    <button
                                      type="button"
                                      className="secondary-btn"
                                      disabled={isRunningTurn || !canAdoptToComposer}
                                      title={!canAdoptToComposer ? "Nur direkte Ausfuehrung verfuegbar" : undefined}
                                      onClick={() => adoptClarifyCandidateIntoComposer(candidate)}
                                    >
                                      In Struktur-Aktion
                                    </button>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </section>
              ) : null}

              <form className="turn-form" onSubmit={handleTurnSubmit}>
                <label>
                  Spieler-Eingabe
                  <textarea
                    rows={3}
                    value={turnInput}
                    onChange={(event) => setTurnInput(event.target.value)}
                    placeholder="Ich gehe zur Taverne und spreche mit dem Wirt."
                  />
                </label>
                <div className="turn-actions">
                  <button className="primary-btn" type="submit" disabled={isRunningTurn}>
                    {isRunningTurn ? "Verarbeite..." : "Turn senden"}
                  </button>
                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={() => setTurnInput("Ich schaue mich vorsichtig um und suche nach Hinweisen.")}
                    disabled={isRunningTurn}
                  >
                    Beispielzug einsetzen
                  </button>
                </div>
              </form>

              <section className="subpanel">
                <h3>Struktur-Aktion (G10)</h3>
                <div className="turn-actions">
                  <label className="compact-label">
                    Aktion
                    <select
                      className="compact-input"
                      value={composerActionKind}
                      onChange={(event) => {
                        setComposerActionKind(event.target.value as StructuredActionKind);
                        setComposerTargetRef("");
                      }}
                      disabled={isRunningTurn}
                    >
                      <option value="TALK">Talk</option>
                      <option value="MOVE">Move</option>
                      <option value="APPROACH">Approach</option>
                      <option value="RETREAT">Retreat</option>
                      <option value="ATTACK">Attack</option>
                      <option value="USE_ITEM">Use Item</option>
                    </select>
                  </label>
                  {composerActionKind === "ATTACK" ? (
                    <label className="compact-label">
                      Angriffstyp
                      <select
                        className="compact-input"
                        value={composerAttackMode}
                        onChange={(event) => setComposerAttackMode(event.target.value as "melee" | "ranged")}
                        disabled={isRunningTurn}
                      >
                        <option value="melee">Nahkampf</option>
                        <option value="ranged">Fernkampf</option>
                      </select>
                    </label>
                  ) : null}
                  <label className="compact-label" style={{ minWidth: 260 }}>
                    Ziel
                    <select
                      className="compact-input"
                      value={composerTargetRef}
                      onChange={(event) => setComposerTargetRef(event.target.value)}
                      disabled={isRunningTurn || composerTargets.length === 0}
                    >
                      <option value="">
                        {composerTargets.length === 0 ? "Keine Ziele" : "Bitte waehlen (oder erstes auto)"}
                      </option>
                      {composerTargets.map((target) => (
                        <option key={target.refId} value={target.refId}>
                          {target.name} [{target.refId}]
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={() => void handleStructuredTurnSubmit()}
                    disabled={isRunningTurn || composerTargets.length === 0 || Boolean(composerDistanceActionBlockedReason)}
                    title={composerDistanceActionBlockedReason || undefined}
                  >
                    {isRunningTurn ? "Verarbeite..." : "Struktur-Turn senden"}
                  </button>
                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={() => {
                      const selected =
                        composerTargets.find((entry) => entry.refId === composerTargetRef) || composerTargets[0];
                      if (selected) {
                        enqueueStructuredAction(composerActionKind, selected);
                      }
                    }}
                    disabled={isRunningTurn || composerTargets.length === 0 || Boolean(composerDistanceActionBlockedReason)}
                    title={composerDistanceActionBlockedReason || undefined}
                  >
                    Zur Queue
                  </button>
                </div>
                {composerTargets[0] ? (
                  <>
                    <p className="list-subtle">
                      ID-basierter Turn ueber `actions_override`. Freitext bleibt optional parallel nutzbar.
                    </p>
                    {selectedComposerTarget &&
                    (composerActionKind === "APPROACH" || composerActionKind === "RETREAT") ? (
                      <p className="list-subtle">
                        Distanzstatus {selectedComposerTarget.name}:{" "}
                        {distanceBandDisplayLabel(selectedComposerTarget.distanceBandToPlayer)}.{" "}
                        {distanceActionHint(selectedComposerTarget.distanceBandToPlayer)}
                      </p>
                    ) : null}
                    {composerDistanceActionBlockedReason ? (
                      <p className="list-subtle">{composerDistanceActionBlockedReason}</p>
                    ) : null}
                  </>
                ) : null}
                <div className="turn-actions">
                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={() => void handleQueueSubmit()}
                    disabled={isRunningTurn || structuredQueue.length === 0}
                  >
                    {isRunningTurn ? "Verarbeite..." : `Queue senden (${structuredQueue.length})`}
                  </button>
                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={() => setStructuredQueue([])}
                    disabled={isRunningTurn || structuredQueue.length === 0}
                  >
                    Queue leeren
                  </button>
                </div>
                <div className="turn-actions">
                  <label className="compact-label">
                    Queue-Makro
                    <input
                      className="compact-input"
                      value={queueMacroName}
                      onChange={(event) => setQueueMacroName(event.target.value)}
                      placeholder="z.B. Marktgespraech"
                      disabled={isRunningTurn}
                    />
                  </label>
                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={() => saveCurrentQueueAsMacro()}
                    disabled={isRunningTurn || structuredQueue.length === 0}
                  >
                    Makro speichern
                  </button>
                </div>
                {queueMacros.length > 0 ? (
                  <ul className="list list-tight">
                    {queueMacros.map((macro) => (
                      <li key={macro.name}>
                        <span className="list-title">
                          {macro.name} ({macro.entries.length})
                        </span>
                        <div className="turn-actions">
                          <button
                            type="button"
                            className="secondary-btn"
                            onClick={() => loadQueueMacro(macro.name)}
                            disabled={isRunningTurn}
                          >
                            Laden
                          </button>
                          <button
                            type="button"
                            className="secondary-btn"
                            onClick={() => deleteQueueMacro(macro.name)}
                            disabled={isRunningTurn}
                          >
                            Loeschen
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : null}
                {structuredQueue.length > 0 ? (
                  <ul className="list list-tight">
                    {structuredQueue.map((entry, index) => (
                      <li key={`${entry.label}-${index}`}>
                        <span className="list-title">{index + 1}. {entry.label}</span>
                        <div className="turn-actions">
                          <button
                            type="button"
                            className="secondary-btn"
                            onClick={() => moveQueuedAction(index, -1)}
                            disabled={isRunningTurn || index === 0}
                          >
                            Hoch
                          </button>
                          <button
                            type="button"
                            className="secondary-btn"
                            onClick={() => moveQueuedAction(index, 1)}
                            disabled={isRunningTurn || index === structuredQueue.length - 1}
                          >
                            Runter
                          </button>
                          <button
                            type="button"
                            className="secondary-btn"
                            onClick={() => removeQueuedAction(index)}
                            disabled={isRunningTurn}
                          >
                            Entfernen
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </section>

              <div className="split-columns">
                <section className="subpanel">
                  <h3>Turn-Verlauf</h3>
                  <ul className="list list-tight">
                    {context.recent_turns.length === 0 ? <li>Noch keine Turns.</li> : null}
                    {context.recent_turns
                      .slice()
                      .reverse()
                      .map((turn) => (
                        <li key={turn.turn_id}>
                          <p className="list-title">{turn.raw_player_input}</p>
                          {turn.resolution.system_events.length === 0 ? (
                            <p className="list-subtle">Keine Events</p>
                          ) : (
                            <div className="event-list">
                                  {turn.resolution.system_events.map((event, index) => (
                                <div key={`${turn.turn_id}-${event.code}-${index}`} className="event-row">
                                  <span className={`event-group-badge ${eventGroupClass(event.code)}`}>
                                    {eventGroupLabel(event.code)}
                                  </span>
                                  <span className={`event-badge event-${event.severity}`}>{event.code}</span>
                                  {(() => {
                                    const skillCheckSummary = getSkillCheckEventSummary(event);
                                    if (!skillCheckSummary) {
                                      return <span className="event-message">{event.message}</span>;
                                    }
                                    return (
                                      <div className="skillcheck-summary">
                                        <div className="skillcheck-badges">
                                          <span
                                            className={`skillcheck-badge ${skillCheckSummary.success ? "skillcheck-success" : "skillcheck-fail"}`}
                                          >
                                            {skillCheckSummary.success ? "Erfolg" : "Misserfolg"}
                                          </span>
                                          <span className="skillcheck-badge">W20 {skillCheckSummary.roll}</span>
                                          <span className="skillcheck-badge">Mod {formatSignedNumber(skillCheckSummary.modifier)}</span>
                                          <span className="skillcheck-badge">DC {skillCheckSummary.dc}</span>
                                          <span className="skillcheck-badge">Total {skillCheckSummary.total}</span>
                                        </div>
                                        <span className="event-message">
                                          Probe {skillCheckSummary.label} ({skillCheckSummary.attribute} {skillCheckSummary.attributeScore})
                                        </span>
                                      </div>
                                    );
                                  })()}
                                  {event.code === "clarify_required" ? (
                                    (() => {
                                      const candidates = normalizeClarifyCandidates(event);
                                      const suggestedAction =
                                        typeof event.clarify?.suggested_action === "string"
                                          ? event.clarify.suggested_action
                                          : typeof event.metadata?.suggested_action === "string"
                                            ? event.metadata.suggested_action
                                            : "";
                                      const clarifyReason =
                                        typeof event.clarify?.reason === "string"
                                          ? event.clarify.reason
                                          : typeof event.metadata?.reason === "string"
                                            ? event.metadata.reason
                                            : "";
                                      const groupedCandidates = groupClarifyCandidates(candidates);
                                      return (
                                        <div className="turn-actions">
                                          {clarifyReason ? (
                                            <span className="npc-badge npc-badge-vorsichtig">
                                              Rueckfrage: {clarifyReasonLabel(clarifyReason)}
                                            </span>
                                          ) : null}
                                          {suggestedAction === "inspect_broad" ? (
                                            <button
                                              type="button"
                                              className="secondary-btn"
                                              disabled={isRunningTurn}
                                              onClick={() => void runBroadInspectQuickAction()}
                                            >
                                              Umsehen
                                            </button>
                                          ) : null}
                                          {groupedCandidates.map((group, groupIndex) => (
                                            <div key={`${turn.turn_id}-${event.code}-${index}-group-${groupIndex}`} className="clarify-group">
                                              <span className="list-subtle">{group.label}</span>
                                              <div className="turn-actions">
                                                {group.items.slice(0, 4).map((candidate, candidateIndex) => (
                                                  <button
                                                    key={`${turn.turn_id}-${event.code}-${index}-cand-${groupIndex}-${candidateIndex}`}
                                                    type="button"
                                                    className="secondary-btn"
                                                    disabled={isRunningTurn}
                                                    title={clarifyCandidateSubtitle(candidate) || undefined}
                                                    onClick={() =>
                                                      void executeStructuredActions(
                                                        [
                                                          {
                                                            label: `Clarify: ${candidate.label || candidate.name || candidate.target_ref}`,
                                                            action: buildClarifyCandidateAction(candidate),
                                                          },
                                                        ],
                                                        "Quick Action",
                                                      )
                                                    }
                                                  >
                                                    {candidate.label || candidate.name || candidate.target_ref}
                                                  </button>
                                                ))}
                                              </div>
                                              {group.items.slice(0, 2).map((candidate, subtitleIndex) => {
                                                const subtitle = clarifyCandidateSubtitle(candidate);
                                                if (!subtitle) {
                                                  return null;
                                                }
                                                return (
                                                  <p
                                                    key={`${turn.turn_id}-${event.code}-${index}-sub-${groupIndex}-${subtitleIndex}`}
                                                    className="list-subtle"
                                                  >
                                                    {candidate.label || candidate.name || candidate.target_ref}: {subtitle}
                                                  </p>
                                                );
                                              })}
                                            </div>
                                          ))}
                                        </div>
                                      );
                                    })()
                                  ) : null}
                                </div>
                              ))}
                            </div>
                          )}
                        </li>
                      ))}
                  </ul>
                </section>

                <section className="subpanel">
                  <h3>Journal (letzte Eintraege)</h3>
                  <ul className="list">
                    {context.recent_journal
                      .slice()
                      .reverse()
                      .map((entry) => (
                        <li key={entry.journal_entry_id}>
                          <p className="list-title">{entry.entry_type}</p>
                          <p className="list-subtle">{entry.text}</p>
                        </li>
                      ))}
                  </ul>
                </section>
              </div>
            </>
          )}

          {lastActionMessage ? <p className="info-text">{lastActionMessage}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}
        </article>

        <article className="panel">
          <h2>Charaktersheet</h2>
          {!context ? (
            <p>Welt starten, dann wird der Charakterstatus angezeigt.</p>
          ) : (
            <>
              <p className="section-caption">{context.world.character_state.name}</p>
              <ul className="list">
                <li>Level: {context.world.character_state.level}</li>
                <li>XP: {context.world.character_state.xp}</li>
                <li>Ort: {context.world.character_state.location_name}</li>
                <li>Zone: {context.world.character_state.scene_zone_name}</li>
                <li>
                  HP: {context.world.character_state.resources.hp}/{context.world.character_state.resources.max_hp}
                </li>
                <li>
                  Ausdauer: {context.world.character_state.resources.stamina}/
                  {context.world.character_state.resources.max_stamina}
                </li>
                <li>
                  Fokus: {context.world.character_state.resources.focus}/{context.world.character_state.resources.max_focus}
                </li>
              </ul>
              <h3>Attribute</h3>
              <ul className="list list-tight">
                {Object.entries(context.world.character_state.attributes).map(([name, value]) => (
                  <li key={name}>
                    {name}: {value}
                  </li>
                ))}
              </ul>
              {context.quests.length > 0 ? (
                <>
                  <h3>Questlog (MVP)</h3>
                  <ul className="list">
                    {context.quests.map((quest) => (
                      <li key={quest.quest_id}>
                        <p className="list-title">
                          {quest.title} ({quest.status})
                        </p>
                        <p className="list-subtle">Stage: {quest.current_stage}</p>
                        <ul className="list list-tight">
                          {quest.objectives.map((objective) => (
                            <li key={objective.objective_id}>
                              <span>
                                [{objective.status}] {objective.title}
                              </span>
                              {objective.hint ? <p className="list-subtle">{objective.hint}</p> : null}
                            </li>
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              {context.story_flags && Object.keys(context.story_flags).length > 0 ? (
                <>
                  <h3>Story-Flags (MVP)</h3>
                  <ul className="list list-tight">
                    {Object.entries(context.story_flags)
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([flagKey, flagValue]) => (
                        <li key={flagKey}>
                          {flagKey}: {String(flagValue)}
                        </li>
                      ))}
                  </ul>
                </>
              ) : null}
            </>
          )}
        </article>

        <article className="panel">
          <h2>Inventar & NPC Memory</h2>
          {!context ? (
            <p>Nach dem World-Bootstrap erscheinen Inventar und NPC-Kontext.</p>
          ) : (
            <>
              <h3>Inventar</h3>
              <ul className="list list-tight">
                {context.world.inventory.map((item) => (
                  <li key={item.inventory_item_id}>
                    <span className="list-title">
                      {item.name} x{item.quantity}
                    </span>
                    <span className="list-subtle">{item.use_modes.join(", ")} | {item.inventory_item_id}</span>
                    <div className="turn-actions">
                      <button
                        type="button"
                        className="secondary-btn"
                        disabled={
                          isRunningTurn ||
                          item.quantity <= 0 ||
                          (!item.use_modes.includes("use") && !item.use_modes.includes("consume"))
                        }
                        onClick={() =>
                          void executeStructuredActions(
                            [
                              {
                                label: buildStructuredActionLabel("USE_ITEM", {
                                  refId: item.inventory_item_id,
                                  name: item.name,
                                  kind: "item",
                                  auxiliary: item.use_modes.join(", "),
                                }),
                                action: buildStructuredAction("USE_ITEM", {
                                  refId: item.inventory_item_id,
                                  name: item.name,
                                  kind: "item",
                                  auxiliary: item.use_modes.join(", "),
                                }),
                              },
                            ],
                            "Quick Action",
                          )
                        }
                      >
                        Use
                      </button>
                    </div>
                  </li>
                ))}
              </ul>

              <h3>NPC Memory (Retrieval)</h3>
              {context.retrieval_notes.length > 0 ? (
                <p className="list-subtle">{context.retrieval_notes.join(" | ")}</p>
              ) : null}
              <ul className="list">
                {context.npc_memory.length === 0 ? <li>Noch keine NPC-Erinnerungen.</li> : null}
                {context.npc_memory.map((entry) => (
                  (() => {
                    const npcRef = context.target_catalog.npcs.find((n) => n.ref_id === entry.bundle.profile.npc_id);
                    const npcDistance = npcRef?.distance_band_to_player || undefined;
                    const quickNpcTarget: StructuredTarget = {
                      refId: entry.bundle.profile.npc_id,
                      name: entry.bundle.profile.name,
                      kind: "npc",
                      role: entry.bundle.profile.role,
                      locationName: entry.bundle.profile.location_name || context.world.character_state.location_name,
                      sceneZoneId: entry.bundle.profile.scene_zone_id || undefined,
                      sceneZoneName: entry.bundle.profile.scene_zone_name || undefined,
                      distanceBandToPlayer: npcDistance,
                      standing: entry.bundle.relationship?.standing,
                    };
                    const disableApproach = isRunningTurn || isApproachNotNeeded(npcDistance);
                    const disableRetreat = isRunningTurn || isRetreatNotNeeded(npcDistance);
                    const dialogTopicOptions = parseDialogTopicOptions(npcRef?.discovery_state?.dialog_topics_json);
                    return (
                      <li key={entry.bundle.profile.npc_id}>
                        <p className="list-title">
                          {entry.bundle.profile.name} ({entry.bundle.profile.role})
                        </p>
                        <p className="list-subtle">
                          ID: {entry.bundle.profile.npc_id} |{" "}
                          Score: {entry.relevance_score.toFixed(2)}
                          {entry.bundle.relationship ? ` | Standing: ${entry.bundle.relationship.standing}` : ""}
                          {entry.bundle.profile.faction ? ` | Fraktion: ${entry.bundle.profile.faction}` : ""}
                        </p>
                        <p className="list-subtle">
                          Ort/Zone: {entry.bundle.profile.location_name || context.world.character_state.location_name} /{" "}
                          {entry.bundle.profile.scene_zone_name || "Unbekannt"} | Distanz:{" "}
                          {distanceBandDisplayLabel(npcDistance)}
                        </p>
                        <div className="npc-badge-row">
                          <span
                            className={`npc-badge ${reactionStyleBadgeClass(
                              entry.bundle.profile.role,
                              entry.bundle.relationship?.standing,
                            )}`}
                          >
                            {reactionStyleLabel(entry.bundle.profile.role, entry.bundle.relationship?.standing)}
                          </span>
                          <span className="npc-badge npc-badge-distance">
                            Distanz: {distanceBandDisplayLabel(npcDistance)}
                          </span>
                        </div>
                        <p className="list-subtle">{distanceActionHint(npcDistance)}</p>
                        {typeof npcRef?.discovery_state?.dialog_hint === "string" &&
                        npcRef.discovery_state.dialog_hint.trim() ? (
                          <p className="list-subtle">Hinweis: {String(npcRef.discovery_state.dialog_hint)}</p>
                        ) : null}
                        {typeof npcRef?.discovery_state?.dialog_state === "string" &&
                        npcRef.discovery_state.dialog_state.trim() ? (
                          <p className="list-subtle">
                            Dialogzustand: {String(npcRef.discovery_state.dialog_state)}
                          </p>
                        ) : null}
                        {typeof npcRef?.discovery_state?.dialog_topics_hint === "string" &&
                        npcRef.discovery_state.dialog_topics_hint.trim() ? (
                          <p className="list-subtle">
                            Themen: {String(npcRef.discovery_state.dialog_topics_hint)}
                          </p>
                        ) : null}
                        {dialogTopicOptions.length > 0 ? (
                          <div className="turn-actions">
                            {dialogTopicOptions.map((topic) => (
                              <button
                                key={`${entry.bundle.profile.npc_id}:${topic.topic_id}`}
                                type="button"
                                className="secondary-btn"
                                disabled={isRunningTurn}
                                title={topic.summary || topic.label}
                                onClick={() =>
                                  void executeStructuredActions(
                                    [
                                      {
                                        label: `Topic: ${entry.bundle.profile.name} / ${topic.label}`,
                                        action: buildTalkTopicAction(quickNpcTarget, topic),
                                      },
                                    ],
                                    "Dialog-Topic",
                                  )
                                }
                              >
                                {typeof topic.dialog_tree_step === "number" && Number.isFinite(topic.dialog_tree_step)
                                  ? `${topic.dialog_tree_step}. ${topic.label}`
                                  : topic.label}
                              </button>
                            ))}
                          </div>
                        ) : null}
                        {dialogTopicOptions.length > 0 ? (
                          <div className="list-subtle">
                            {dialogTopicOptions.map((topic) => (
                              <div key={`${entry.bundle.profile.npc_id}:${topic.topic_id}:meta`}>
                                Topic {topic.label}
                                {topic.followup_of ? ` | Folge von: ${topic.followup_of}` : ""}
                                {topic.followup_condition ? ` | Branch: ${topic.followup_condition}` : ""}
                                {topic.future_check_label || topic.future_check_attribute
                                  ? ` | Probe: ${topic.future_check_label || topic.future_check_attribute}${
                                      typeof topic.future_check_dc === "number" && Number.isFinite(topic.future_check_dc)
                                        ? ` (DC ${topic.future_check_dc})`
                                        : ""
                                    }`
                                  : ""}
                                {topic.effect_hint ? ` | Effekt: ${topic.effect_hint}` : ""}
                              </div>
                            ))}
                          </div>
                        ) : null}
                        {entry.bundle.recent_memories[0] ? (
                          <p className="list-subtle">{entry.bundle.recent_memories[0].summary}</p>
                        ) : null}
                        <div className="turn-actions">
                      <button
                        type="button"
                        className="secondary-btn"
                        disabled={isRunningTurn}
                        onClick={() =>
                          void executeStructuredActions(
                            [
                              {
                                label: buildStructuredActionLabel("TALK", {
                                  ...quickNpcTarget,
                                }),
                                action: buildStructuredAction("TALK", quickNpcTarget),
                              },
                            ],
                            "Quick Action",
                          )
                        }
                      >
                        Talk
                      </button>
                      <button
                        type="button"
                        className="secondary-btn"
                        disabled={isRunningTurn}
                        onClick={() =>
                          void executeStructuredActions(
                            [
                              {
                                label: `Gehe zu + rede mit ${entry.bundle.profile.name}`,
                                action: buildStructuredAction("TALK", quickNpcTarget),
                              },
                            ],
                            "Quick Action",
                          )
                        }
                      >
                        Gehe+Rede
                      </button>
                      <button
                        type="button"
                        className="secondary-btn"
                        disabled={disableApproach}
                        title={disableApproach ? "Annaehern nicht noetig (bereits adjacent)." : undefined}
                        onClick={() =>
                          void executeStructuredActions(
                            [
                              {
                                label: buildStructuredActionLabel("APPROACH", quickNpcTarget),
                                action: buildStructuredAction("APPROACH", quickNpcTarget),
                              },
                            ],
                            "Quick Action",
                          )
                        }
                      >
                        {approachButtonLabel(npcDistance)}
                      </button>
                      <button
                        type="button"
                        className="secondary-btn"
                        disabled={disableRetreat}
                        title={disableRetreat ? "Abstand nicht noetig (bereits far/unreachable)." : undefined}
                        onClick={() =>
                          void executeStructuredActions(
                            [
                              {
                                label: buildStructuredActionLabel("RETREAT", quickNpcTarget),
                                action: buildStructuredAction("RETREAT", quickNpcTarget),
                              },
                            ],
                            "Quick Action",
                          )
                        }
                      >
                        {retreatButtonLabel(npcDistance)}
                      </button>
                      <button
                        type="button"
                        className="secondary-btn"
                        disabled={isRunningTurn}
                        onClick={() =>
                          enqueueStructuredAction("ATTACK", {
                            ...quickNpcTarget,
                          })
                        }
                      >
                        +Attack Queue
                      </button>
                        </div>
                      </li>
                    );
                  })()
                ))}
              </ul>

              <h3>Ziel-Referenzen</h3>
              <ul className="list list-tight">
                {context.target_catalog.locations.slice(0, 5).map((location) => (
                  <li key={location.ref_id}>
                    <span className="list-title">{location.name}</span>
                    <span className="list-subtle">
                      {location.ref_id}
                      {location.scene_zone_name ? ` | Zone: ${location.scene_zone_name}` : ""}
                    </span>
                    <div className="turn-actions">
                      <button
                        type="button"
                        className="secondary-btn"
                        disabled={isRunningTurn}
                        onClick={() =>
                          void executeStructuredActions(
                            [
                              {
                                label: buildStructuredActionLabel("MOVE", {
                                  refId: location.ref_id,
                                  name: location.name,
                                  kind: "location",
                                }),
                                action: buildStructuredAction("MOVE", {
                                  refId: location.ref_id,
                                  name: location.name,
                                  kind: "location",
                                }),
                              },
                            ],
                            "Quick Action",
                          )
                        }
                      >
                        Move
                      </button>
                    </div>
                  </li>
                ))}
              </ul>

              <h3>Interaktionspunkte (sichtbar)</h3>
              <p className="list-subtle">
                Sichtbar: {context.target_catalog.scene_points.length} | Detail verifiziert:{" "}
                {context.target_catalog.scene_points.filter((point) => (point.detail_level || 1) >= 2).length}
                {" | "}Verborgene Punkte: {context.discovery_counts?.hidden_scene_point_count || 0} | Verborgene NPCs:{" "}
                {context.discovery_counts?.hidden_npc_count || 0}
              </p>
              {context.target_catalog.scene_points.length > 0 ? (
                <div className="turn-actions">
                  <label className="list-subtle">
                    Filter{" "}
                    <select value={scenePointFilter} onChange={(e) => setScenePointFilter(e.target.value as ScenePointFilter)}>
                      <option value="all">Alle</option>
                      <option value="unknown">Nur unklar</option>
                      <option value="container">Container</option>
                      <option value="scene_object">Objekte</option>
                      <option value="scene_point">Punkte</option>
                    </select>
                  </label>
                  <label className="list-subtle">
                    Sortierung{" "}
                    <select value={scenePointSort} onChange={(e) => setScenePointSort(e.target.value as ScenePointSort)}>
                      <option value="name">Name</option>
                      <option value="detail">Detail</option>
                      <option value="zone">Zone</option>
                    </select>
                  </label>
                </div>
              ) : null}
              <ul className="list list-tight">
                {scenePointsForDisplay.length === 0 ? (
                  <li>
                    <span className="list-subtle">
                      {context.target_catalog.scene_points.length === 0
                        ? "Keine sichtbaren Interaktionspunkte. Umsehen/Untersuchen kann neue Punkte aufdecken."
                        : "Keine Interaktionspunkte fuer den aktuellen Filter."}
                    </span>
                  </li>
                ) : null}
                {scenePointsForDisplay.map((point) => (
                  <li key={point.ref_id}>
                    <span className="list-title">{point.name}</span>
                    <span className="list-subtle">
                      {(point.detail_level || 1) >= 2 ? point.kind : "unbekannt"}
                      {" | "}
                      {point.ref_id}
                      {point.scene_zone_name ? ` | Zone: ${point.scene_zone_name}` : ""}
                      {point.detail_level ? ` | Details: ${point.detail_level}` : ""}
                    </span>
                    <div className="npc-badge-row">
                      <span className={`npc-badge ${(point.detail_level || 1) >= 2 ? "npc-badge-friendly" : "npc-badge-cautious"}`}>
                        {(point.detail_level || 1) >= 2 ? "Discovery: Details verifiziert" : "Discovery: Sichtbar, aber unklar"}
                      </span>
                      {point.kind === "container" && (point.detail_level || 1) >= 2 ? (
                        <span className="npc-badge npc-badge-distance">
                          Container:{" "}
                          {point.discovery_state?.looted
                            ? "durchsucht"
                            : point.discovery_state?.opened
                              ? "geoeffnet"
                              : "geschlossen"}
                        </span>
                      ) : null}
                      {point.kind === "scene_object" && (point.detail_level || 1) >= 2 ? (
                        <span className="npc-badge npc-badge-distance">
                          Objekt: {point.discovery_state?.taken ? "mitgenommen" : "verfuegbar"}
                        </span>
                      ) : null}
                    </div>
                    {(point.detail_level || 1) >= 2 && point.discovery_state ? (
                      <p className="list-subtle">
                        {point.kind === "container"
                          ? `Containerstatus: ${
                              point.discovery_state.looted
                                ? "durchsucht"
                                : point.discovery_state.opened
                                  ? "geoeffnet"
                                  : "geschlossen"
                            }`
                          : "Details durch Untersuchung verifiziert."}
                      </p>
                    ) : (
                      <p className="list-subtle">Untersuche den Punkt gezielt, um Typ und Details zu bestaetigen.</p>
                    )}
                    <div className="turn-actions">
                      {point.kind === "scene_object" ? (
                        <button
                          type="button"
                          className="secondary-btn"
                          disabled={isRunningTurn || (point.detail_level || 1) < 2 || Boolean(point.discovery_state?.taken)}
                          title={
                            (point.detail_level || 1) < 2
                              ? "Erst gezielt untersuchen, um das Objekt sicher zu identifizieren."
                              : point.discovery_state?.taken
                                ? "Objekt wurde bereits mitgenommen."
                                : undefined
                          }
                          onClick={() =>
                            void executeStructuredActions(
                              [
                                {
                                  label: `Nimm ${point.name}`,
                                  action: {
                                    action_type: "TAKE",
                                    target_ref: point.ref_id,
                                    target_kind: "scene_object",
                                    parameters: {
                                      intent: "take",
                                      target_id: point.ref_id,
                                      target_name: point.name,
                                      target_kind: "scene_object",
                                      target_detail_level: point.detail_level || 1,
                                    },
                                    confidence: 0.99,
                                  },
                                },
                              ],
                              "Quick Action",
                            )
                          }
                        >
                          {(point.detail_level || 1) < 2 ? "Nehmen (erst Inspect)" : "Nehmen"}
                        </button>
                      ) : null}
                      {point.kind === "container" ? (
                        <>
                          <button
                            type="button"
                            className="secondary-btn"
                            disabled={isRunningTurn || (point.detail_level || 1) < 2 || Boolean(point.discovery_state?.opened)}
                            title={
                              (point.detail_level || 1) < 2
                                ? "Erst gezielt untersuchen, um den Behaelter sicher zu identifizieren."
                                : point.discovery_state?.opened
                                  ? "Container ist bereits geoeffnet."
                                  : undefined
                            }
                            onClick={() =>
                              void executeStructuredActions(
                                [
                                  {
                                    label: `Oeffne ${point.name}`,
                                    action: {
                                      action_type: "OPEN",
                                      target_ref: point.ref_id,
                                      target_kind: "container",
                                      parameters: {
                                        intent: "open",
                                        target_id: point.ref_id,
                                        target_name: point.name,
                                        target_kind: "container",
                                        target_detail_level: point.detail_level || 1,
                                      },
                                      confidence: 0.99,
                                    },
                                  },
                                ],
                                "Quick Action",
                              )
                            }
                          >
                            {(point.detail_level || 1) < 2 ? "Oeffnen (erst Inspect)" : "Oeffnen"}
                          </button>
                          <button
                            type="button"
                            className="secondary-btn"
                            disabled={isRunningTurn || (point.detail_level || 1) < 2}
                            title={
                              (point.detail_level || 1) < 2
                                ? "Erst gezielt untersuchen, um den Behaelter sicher zu identifizieren."
                                : undefined
                            }
                            onClick={() =>
                              void executeStructuredActions(
                                [
                                  {
                                    label: `Durchsuche ${point.name}`,
                                    action: {
                                      action_type: "SEARCH",
                                      target_ref: point.ref_id,
                                      target_kind: "container",
                                      parameters: {
                                        intent: "search",
                                        target_id: point.ref_id,
                                        target_name: point.name,
                                        target_kind: "container",
                                        target_detail_level: point.detail_level || 1,
                                      },
                                      confidence: 0.99,
                                    },
                                  },
                                ],
                                "Quick Action",
                              )
                            }
                          >
                            {(point.detail_level || 1) < 2 ? "Durchsuchen (erst Inspect)" : "Durchsuchen"}
                          </button>
                        </>
                      ) : null}
                      <button
                        type="button"
                        className="secondary-btn"
                        disabled={isRunningTurn}
                        onClick={() =>
                          void executeStructuredActions(
                            [
                              {
                                label: `Untersuche ${point.name}`,
                                action: {
                                  action_type: "INSPECT",
                                  target_ref: point.ref_id,
                                  target_kind: "scene_point",
                                  parameters: {
                                    intent: "inspect",
                                    target_id: point.ref_id,
                                    target_name: point.name,
                                    target_kind: "scene_point",
                                    inspect_mode: "focused",
                                  },
                                  confidence: 0.99,
                                },
                              },
                            ],
                            "Quick Action",
                          )
                        }
                      >
                        Inspect
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </article>
      </section>
    </main>
  );
}
