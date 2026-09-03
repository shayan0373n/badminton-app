/**
 * Every management action for the night, in one drawer.
 *
 * This is the old Streamlit sidebar: add and remove people, change courts and
 * weights, upload results, end the session. It lives on the check-in hub so the
 * playing screen can stay free of controls.
 */

import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Stepper } from "./Stepper";
import type { RegistryPlayer, Session } from "../types";

/** How many names the drawer will list before it insists on a search. */
const REGISTRY_LIST_MAX = 12;

/** Optimizer keys paired with what they mean to whoever is running the night. */
const WEIGHT_LABELS = [
  ["skill", "Even courts"],
  ["power", "Even teams"],
  ["pairing", "Vary partners"],
] as const;

interface Props {
  session: Session;
  busy: boolean;
  run: (
    action: () => Promise<Session>,
    options?: { optimistic?: (s: Session) => Session; blocking?: boolean },
  ) => Promise<Session | null>;
  onClose: () => void;
  onExit: () => void;
}

export function SideMenu({ session, busy, run, onClose, onExit }: Props) {
  const [registry, setRegistry] = useState<RegistryPlayer[]>([]);
  const [registryFilter, setRegistryFilter] = useState("");
  const [guestName, setGuestName] = useState("");
  const [guestGender, setGuestGender] = useState<"M" | "F">("M");
  const [guestMu, setGuestMu] = useState("25");
  const [courts, setCourts] = useState(session.num_courts);
  const [weights, setWeights] = useState<Record<string, number>>(session.weights);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmEnd, setConfirmEnd] = useState(false);

  const name = session.name;
  const onList = new Set(session.candidates.map((c) => c.name));
  const weightsChanged = WEIGHT_LABELS.some(
    ([key]) => weights[key] !== session.weights[key],
  );

  useEffect(() => {
    api
      .listPlayers()
      .then((r) => setRegistry(r.players))
      .catch(() => setRegistry([]));
  }, []);

  useEffect(() => {
    // Escape is the fastest way out when the drawer is in the way.
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const available = useMemo(() => {
    const needle = registryFilter.trim().toLowerCase();
    const pool = registry.filter((p) => !onList.has(p.name));
    return needle ? pool.filter((p) => p.name.toLowerCase().includes(needle)) : pool;
    // onList is rebuilt every render; the candidate names are what actually matter.
  }, [registry, registryFilter, session.candidates]);

  // The club registry runs to hundreds of names. Listing them all buries the
  // rest of the drawer, so past a drawer-full you have to narrow it first.
  const searching = registryFilter.trim().length > 0;
  const listed = searching || available.length <= REGISTRY_LIST_MAX ? available : [];

  async function submitResults() {
    setNotice(null);
    try {
      const result = await api.submit(name);
      setNotice(
        `Uploaded ${result.recorded} match${result.recorded === 1 ? "" : "es"}` +
          (result.unreported > 0 ? ` · ${result.unreported} without a winner` : ""),
      );
      await run(() => api.getSession(name));
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Upload failed.");
    }
  }

  return (
    <>
      <button className="scrim" onClick={onClose} aria-label="Close menu" />
      <aside className="drawer" role="dialog" aria-label="Session menu">
        <div className="row" style={{ marginBottom: 16 }}>
          <h2 style={{ flex: 3 }}>Manage session</h2>
          <button className="btn btn-icon" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        {notice && <div className="banner banner-info">{notice}</div>}

        <section className="section">
          <div className="section-head">
            <h2>Courts</h2>
          </div>
          <div className="row">
            <Stepper value={courts} onChange={setCourts} min={1} max={20} label="courts" />
            <button
              className="btn"
              disabled={busy || courts === session.num_courts}
              onClick={() =>
                run(() => api.updateSettings(name, { num_courts: courts }), {
                  blocking: true,
                })
              }
            >
              Apply
            </button>
          </div>
          <p className="hint">From next round.</p>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>Matchmaking weights</h2>
          </div>
          <div className="stack">
            {WEIGHT_LABELS.map(([key, label]) => (
              <div className="field" key={key} style={{ marginBottom: 0 }}>
                <span>{label}</span>
                <Stepper
                  value={weights[key] ?? 1}
                  onChange={(next) => setWeights({ ...weights, [key]: next })}
                  min={0}
                  max={10}
                  step={0.5}
                  label={label.toLowerCase()}
                />
              </div>
            ))}
          </div>
          <button
            className="btn"
            style={{ marginTop: 10 }}
            disabled={busy || !weightsChanged}
            onClick={() =>
              run(() => api.updateSettings(name, { weights }), { blocking: true })
            }
          >
            Apply weights
          </button>
          <p className="hint">Higher weighs more. From next round.</p>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>Add from registry</h2>
          </div>
          <input
            value={registryFilter}
            onChange={(e) => setRegistryFilter(e.target.value)}
            placeholder="Search members…"
            aria-label="Search the registry"
          />
          <div className="stack" style={{ marginTop: 10 }}>
            {listed.map((p) => (
              <div className="row" key={p.name}>
                <span style={{ flex: 3 }}>{p.name}</span>
                <button
                  className="btn btn-icon"
                  disabled={busy}
                  onClick={() =>
                    run(() => api.addCandidate(name, p.name), { blocking: true })
                  }
                  aria-label={`Add ${p.name} to this session`}
                >
                  Add
                </button>
              </div>
            ))}
            {/* Nothing is said when the list is merely too long to show: the
                search box above it is the whole instruction. */}
            {listed.length === 0 && available.length === 0 && (
              <p className="empty">{searching ? "No match." : "All added."}</p>
            )}
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>Add guest</h2>
          </div>
          <div className="stack">
            <input
              placeholder="Name"
              value={guestName}
              onChange={(e) => setGuestName(e.target.value)}
              aria-label="Guest name"
            />
            <div className="row">
              <select
                value={guestGender}
                onChange={(e) => setGuestGender(e.target.value as "M" | "F")}
                aria-label="Guest gender"
              >
                <option value="M">Male</option>
                <option value="F">Female</option>
              </select>
              <input
                type="number"
                step={1}
                value={guestMu}
                onChange={(e) => setGuestMu(e.target.value)}
                aria-label="Starting skill"
              />
            </div>
            <p className="hint">
              Skill: 18 lower · 25 middle · 32 upper.
            </p>
            <button
              className="btn"
              disabled={!guestName.trim() || busy}
              onClick={async () => {
                await run(
                  () =>
                    api.addGuest(name, {
                      name: guestName.trim(),
                      gender: guestGender,
                      mu: Number(guestMu),
                    }),
                  { blocking: true },
                );
                setGuestName("");
              }}
            >
              Add and check in
            </button>
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>Remove players</h2>
          </div>
          <div className="stack">
            {session.candidates.map((c) => (
              <div className="row" key={c.name}>
                <span style={{ flex: 3 }}>{c.name}</span>
                <button
                  className="btn btn-danger btn-icon"
                  disabled={busy}
                  onClick={() => run(() => api.removeCandidate(name, c.name), { blocking: true })}
                  aria-label={`Remove ${c.name} from this session`}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </section>

        {session.is_recorded && (
          <section className="section">
            <div className="section-head">
              <h2>Results</h2>
            </div>
            <button className="btn btn-lg" onClick={submitResults} disabled={busy}>
              Upload results
            </button>
            {session.results_dirty && (
              <p className="hint">Not uploaded yet.</p>
            )}
          </section>
        )}

        <section className="section">
          <div className="section-head">
            <h2>End session</h2>
          </div>
          {confirmEnd ? (
            <div className="stack">
              {session.results_dirty && (
                <div className="banner banner-warn">
                  Unuploaded results will be lost.
                </div>
              )}
              <button
                className="btn btn-danger btn-lg"
                onClick={async () => {
                  await api.deleteSession(name);
                  onExit();
                }}
              >
                End and discard
              </button>
              <button className="btn" onClick={() => setConfirmEnd(false)}>
                Cancel
              </button>
            </div>
          ) : (
            <button className="btn btn-danger btn-lg" onClick={() => setConfirmEnd(true)}>
              End session
            </button>
          )}
        </section>
      </aside>
    </>
  );
}
