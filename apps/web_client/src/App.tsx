import { FormEvent, useMemo, useState } from "react";
import {
  createWorldBootstrap,
  GAME_API_BASE_URL,
  GameContextResponse,
  getWorldContext,
  runTurn,
  StructuredTurnAction,
  TurnRunResponse,
} from "./api";

type BootstrapForm = {
  userId: string;
  worldDescription: string;
  characterDescription: string;
};

type StructuredActionKind = "MOVE" | "TALK" | "ATTACK" | "USE_ITEM";
type StructuredTarget = {
  refId: string;
  name: string;
  kind: string;
  auxiliary?: string;
  locationName?: string;
  sceneZoneId?: string;
  sceneZoneName?: string;
  distanceBandToPlayer?: string;
};
type QueuedStructuredAction = {
  label: string;
  action: StructuredTurnAction;
};

const DEFAULT_BOOTSTRAP: BootstrapForm = {
  userId: "local-dev-user",
  worldDescription:
    "Eine sturmgepeitschte Hafenstadt mit Schmugglern, Nachtmaerkten und rivalisierenden Fraktionen.",
  characterDescription:
    "Eine ehemalige Kartografin, die ihre verschollene Schwester sucht und dafuer mit Informationen handelt.",
};

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
  return context.target_catalog.npcs.map((entry) => ({
    refId: entry.ref_id,
    name: entry.name,
    kind: "npc",
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
  const [composerActionKind, setComposerActionKind] = useState<StructuredActionKind>("TALK");
  const [composerTargetRef, setComposerTargetRef] = useState<string>("");
  const [structuredQueue, setStructuredQueue] = useState<QueuedStructuredAction[]>([]);

  const latestNarrative = useMemo(() => {
    if (!context) {
      return "";
    }
    const latestTurn = context.recent_turns[context.recent_turns.length - 1];
    return latestTurn?.narrative?.narrative || context.world.initial_narrative;
  }, [context]);

  const composerTargets = useMemo(() => {
    if (!context) {
      return [] as Array<{ refId: string; name: string; kind: string; auxiliary?: string }>;
    }
    return getStructuredTargets(context, composerActionKind);
  }, [composerActionKind, context]);

  async function loadContext(targetWorldId: string, retrievalHint?: string): Promise<void> {
    setIsReloading(true);
    setError("");
    try {
      const nextContext = await getWorldContext(targetWorldId, retrievalHint);
      setContext(nextContext);
      setWorldId(targetWorldId);
      setWorldIdInput(targetWorldId);
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
    await loadContext(worldIdInput.trim());
    setLastActionMessage(`Welt geladen: ${worldIdInput.trim()}`);
  }

  async function handleBootstrapSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsBootstrapping(true);
    setError("");
    setLastActionMessage("");
    try {
      const created = await createWorldBootstrap({
        user_id: bootstrapForm.userId.trim(),
        world_description: bootstrapForm.worldDescription.trim(),
        character_description: bootstrapForm.characterDescription.trim(),
      });
      await loadContext(created.world_id);
      setAnalysisNotes([]);
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

  async function applyTurnResult(runResult: TurnRunResponse, fallbackWorldId: string, retrievalHint: string): Promise<void> {
    setAnalysisNotes(runResult.analysis_context_notes || []);
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
    return {
      action_type: actionKind,
      target_ref: target.refId,
      target_kind: "npc",
        parameters: {
          intent: actionKind === "TALK" ? "talk" : "attack",
          target_id: target.refId,
          target_name: target.name,
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
    if (actionKind === "ATTACK") {
      return `UI: Greife ${target.name} an`;
    }
    return `UI: Spreche mit ${target.name}`;
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
              </section>

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
                      <option value="ATTACK">Attack</option>
                      <option value="USE_ITEM">Use Item</option>
                    </select>
                  </label>
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
                    disabled={isRunningTurn || composerTargets.length === 0}
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
                    disabled={isRunningTurn || composerTargets.length === 0}
                  >
                    Zur Queue
                  </button>
                </div>
                {composerTargets[0] ? (
                  <p className="list-subtle">
                    ID-basierter Turn ueber `actions_override`. Freitext bleibt optional parallel nutzbar.
                  </p>
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
                {structuredQueue.length > 0 ? (
                  <ul className="list list-tight">
                    {structuredQueue.map((entry, index) => (
                      <li key={`${entry.label}-${index}`}>
                        <span className="list-title">{index + 1}. {entry.label}</span>
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
                                  <span className={`event-badge event-${event.severity}`}>{event.code}</span>
                                  <span className="event-message">{event.message}</span>
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
                  <li key={entry.bundle.profile.npc_id}>
                    <p className="list-title">
                      {entry.bundle.profile.name} ({entry.bundle.profile.role})
                    </p>
                    <p className="list-subtle">
                      ID: {entry.bundle.profile.npc_id} |{" "}
                      Score: {entry.relevance_score.toFixed(2)}
                      {entry.bundle.relationship ? ` | Standing: ${entry.bundle.relationship.standing}` : ""}
                    </p>
                    <p className="list-subtle">
                      Ort/Zone: {entry.bundle.profile.location_name || context.world.character_state.location_name} /{" "}
                      {entry.bundle.profile.scene_zone_name || "Unbekannt"} | Distanz:{" "}
                      {context.target_catalog.npcs.find((n) => n.ref_id === entry.bundle.profile.npc_id)?.distance_band_to_player || "?"}
                    </p>
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
                                  refId: entry.bundle.profile.npc_id,
                                  name: entry.bundle.profile.name,
                                  kind: "npc",
                                }),
                                action: buildStructuredAction("TALK", {
                                  refId: entry.bundle.profile.npc_id,
                                  name: entry.bundle.profile.name,
                                  kind: "npc",
                                }),
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
                                action: buildStructuredAction("TALK", {
                                  refId: entry.bundle.profile.npc_id,
                                  name: entry.bundle.profile.name,
                                  kind: "npc",
                                  locationName:
                                    entry.bundle.profile.location_name || context.world.character_state.location_name,
                                  sceneZoneId: entry.bundle.profile.scene_zone_id || undefined,
                                  sceneZoneName: entry.bundle.profile.scene_zone_name || undefined,
                                  distanceBandToPlayer:
                                    context.target_catalog.npcs.find((n) => n.ref_id === entry.bundle.profile.npc_id)
                                      ?.distance_band_to_player || undefined,
                                }),
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
                        disabled={isRunningTurn}
                        onClick={() =>
                          enqueueStructuredAction("ATTACK", {
                            refId: entry.bundle.profile.npc_id,
                            name: entry.bundle.profile.name,
                            kind: "npc",
                          })
                        }
                      >
                        +Attack Queue
                      </button>
                    </div>
                  </li>
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
            </>
          )}
        </article>
      </section>
    </main>
  );
}
