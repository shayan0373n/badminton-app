/**
 * Every management action for the night, in one drawer.
 *
 * This is the old Streamlit sidebar: add and remove people, change courts and
 * weights, upload results, end the session. It lives on the check-in hub so the
 * playing screen can stay free of controls.
 */

import { useEffect, useState } from "react";
import { api } from "../api";
import type { RegistryPlayer, Session } from "../types";

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
  const [toAdd, setToAdd] = useState("");
  const [guestName, setGuestName] = useState("");
  const [guestGender, setGuestGender] = useState<"M" | "F">("M");
  const [guestMu, setGuestMu] = useState("25");
  const [courts, setCourts] = useState(String(session.num_courts));
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmEnd, setConfirmEnd] = useState(false);

  const name = session.name;
  const onList = new Set(session.candidates.map((c) => c.name));

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

  const available = registry.filter((p) => !onList.has(p.name));

  async function submitResults() {
    setNotice(null);
    try {
      const result = await api.submit(name);
      setNotice(
        `Uploaded ${result.recorded} match${result.recorded === 1 ? "" : "es"}` +
          (result.unreported > 0
            ? `. ${result.unreported} court${result.unreported === 1 ? "" : "s"} had no winner yet.`
            : "."),
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
          <h2 style={{ flex: 3 }}>Manage night</h2>
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
            <input
              type="number"
              min={1}
              max={20}
              value={courts}
              onChange={(e) => setCourts(e.target.value)}
              aria-label="Number of courts"
            />
            <button
              className="btn"
              disabled={busy || Number(courts) === session.num_courts}
              onClick={() =>
                run(() => api.updateSettings(name, { num_courts: Number(courts) }), {
                  blocking: true,
                })
              }
            >
              Apply
            </button>
          </div>
          <p className="hint">Takes effect from the next round.</p>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>Matchmaking weights</h2>
          </div>
          <div className="stack">
            {(["skill", "power", "pairing"] as const).map((key) => (
              <label className="field" key={key}>
                <span>
                  {key === "skill"
                    ? "Even courts"
                    : key === "power"
                      ? "Even teams"
                      : "Vary partners"}
                </span>
                <input
                  type="number"
                  min={0}
                  max={10}
                  step={0.5}
                  defaultValue={session.weights[key] ?? 1}
                  onBlur={(e) => {
                    const value = Number(e.target.value);
                    if (value !== session.weights[key]) {
                      run(
                        () => api.updateSettings(name, { weights: { [key]: value } }),
                        { blocking: true },
                      );
                    }
                  }}
                />
              </label>
            ))}
          </div>
          <p className="hint">Higher matters more. Applies from the next round.</p>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>Add from registry</h2>
          </div>
          <div className="row">
            <select
              value={toAdd}
              onChange={(e) => setToAdd(e.target.value)}
              aria-label="Registry member"
            >
              <option value="">Choose a member…</option>
              {available.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name}
                </option>
              ))}
            </select>
            <button
              className="btn"
              disabled={!toAdd || busy}
              onClick={async () => {
                await run(() => api.addCandidate(name, toAdd), { blocking: true });
                setToAdd("");
              }}
            >
              Add
            </button>
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>New guest</h2>
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
              Skill: 18 is intermediate-minus, 25 intermediate, 32 intermediate-plus.
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
              Create and check in
            </button>
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>Remove from tonight</h2>
          </div>
          <div className="stack">
            {session.candidates.map((c) => (
              <div className="row" key={c.name}>
                <span style={{ flex: 3 }}>{c.name}</span>
                <button
                  className="btn btn-danger btn-icon"
                  disabled={busy}
                  onClick={() => run(() => api.removeCandidate(name, c.name), { blocking: true })}
                  aria-label={`Remove ${c.name} from tonight`}
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
              Upload results to database
            </button>
            {session.results_dirty && (
              <p className="hint">There are results that haven't been uploaded yet.</p>
            )}
          </section>
        )}

        <section className="section">
          <div className="section-head">
            <h2>End the night</h2>
          </div>
          {confirmEnd ? (
            <div className="stack">
              {session.results_dirty && (
                <div className="banner banner-warn">
                  Some results were never uploaded. Ending now discards them.
                </div>
              )}
              <button
                className="btn btn-danger btn-lg"
                onClick={async () => {
                  await api.deleteSession(name);
                  onExit();
                }}
              >
                Yes, end and discard this session
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
