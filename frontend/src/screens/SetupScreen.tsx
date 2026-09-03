/**
 * Setup: resume a night, or start a new one.
 *
 * Picks who might turn up and how many courts are booked. Nobody is paired here
 * and nobody is checked in yet -- both of those happen on the check-in hub once
 * people actually arrive.
 */

import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Stepper } from "../components/Stepper";
import type { RegistryPlayer, Session, SessionSummary } from "../types";

interface Props {
  onOpen: (session: Session) => void;
}

export function SetupScreen({ onOpen }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [registry, setRegistry] = useState<RegistryPlayer[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [name, setName] = useState("");
  const [courts, setCourts] = useState(2);
  const [recorded, setRecorded] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.listSessions(), api.listPlayers()])
      .then(([s, p]) => {
        setSessions(s.sessions);
        setRegistry(p.players);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load."))
      .finally(() => setLoading(false));
  }, []);

  // Shown as the placeholder and used verbatim on create, so the name the user
  // sees is the one that gets sent.
  const suggestedName = useMemo(() => {
    const taken = new Set(sessions.map((s) => s.name));
    const base = dateName();
    if (!taken.has(base)) return base;
    let n = 2;
    while (taken.has(`${base}-${n}`)) n += 1;
    return `${base}-${n}`;
  }, [sessions]);

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return needle
      ? registry.filter((p) => p.name.toLowerCase().includes(needle))
      : registry;
  }, [registry, filter]);

  function toggle(player: string) {
    setSelected((current) => {
      const next = new Set(current);
      next.has(player) ? next.delete(player) : next.add(player);
      return next;
    });
  }

  async function create() {
    setError(null);
    setBusy(true);
    try {
      const session = await api.createSession({
        name: name.trim() || suggestedName,
        candidates: [...selected],
        num_courts: courts,
        is_doubles: true,
        is_recorded: recorded,
      });
      onOpen(session);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the session.");
    } finally {
      setBusy(false);
    }
  }

  async function resume(sessionName: string) {
    setError(null);
    try {
      onOpen(await api.getSession(sessionName));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open that session.");
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>IranFin Badminton Club Night</h1>
      </header>

      <div className="content">
        {error && <div className="banner banner-error">{error}</div>}
        {loading && <p className="hint">Loading…</p>}

        {sessions.length > 0 && (
          <section className="section">
            <div className="section-head">
              <h2>Active sessions</h2>
            </div>
            {sessions.map((s) => (
              <div className="session-card" key={s.name}>
                <div className="info">
                  <div className="name">{s.name}</div>
                  <div className="meta">
                    {s.round_num > 0 ? `Round ${s.round_num}` : "Not started"} ·{" "}
                    {s.checked_in} of {s.candidates} checked in
                  </div>
                </div>
                <button className="btn btn-primary" onClick={() => resume(s.name)}>
                  Resume
                </button>
              </div>
            ))}
          </section>
        )}

        <section className="section">
          <div className="section-head">
            <h2>New session</h2>
            <span className="count-pill">{selected.size} selected</span>
          </div>

          <label className="field">
            <span>Session name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={suggestedName}
            />
          </label>

          <div className="row" style={{ marginBottom: 12 }}>
            <div className="field" style={{ marginBottom: 0 }}>
              <span>Courts</span>
              <Stepper value={courts} onChange={setCourts} min={1} max={20} label="courts" />
            </div>
            <div className="field" style={{ marginBottom: 0 }}>
              <span>Record to ratings</span>
              <div className="segmented" role="group" aria-label="Record to ratings">
                {[true, false].map((choice) => (
                  <button
                    key={String(choice)}
                    type="button"
                    className={recorded === choice ? "btn btn-primary" : "btn"}
                    onClick={() => setRecorded(choice)}
                    aria-pressed={recorded === choice}
                  >
                    {choice ? "Yes" : "No"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <label className="field">
            <span>Expected players</span>
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Search members…"
            />
          </label>

          <div className="name-grid" style={{ marginBottom: 16 }}>
            {visible.map((player) => (
              <button
                key={player.name}
                type="button"
                className={selected.has(player.name) ? "namebox in" : "namebox"}
                onClick={() => toggle(player.name)}
                aria-pressed={selected.has(player.name)}
              >
                <span className="nb-name">{player.name}</span>
                <span className="nb-meta">
                  {selected.has(player.name) ? "Selected" : "Tap to select"}
                </span>
              </button>
            ))}
          </div>

          {registry.length === 0 && !loading && (
            <p className="empty">
              Registry is empty.
            </p>
          )}

          <div className="cta-sticky">
            <button
              className="btn btn-primary btn-lg"
              disabled={busy || selected.size === 0}
              onClick={create}
            >
              {selected.size === 0
                ? "Select players"
                : `Open check-in with ${selected.size}`}
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}

/** Dated by default, so sessions sort and nobody has to invent a name at the door. */
function dateName(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return `Club-night-${local.toISOString().slice(0, 10)}`;
}
