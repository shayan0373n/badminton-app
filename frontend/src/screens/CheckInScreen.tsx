/**
 * The check-in hub.
 *
 * This is the screen the night runs from: players tap themselves in, long press
 * to ask for a harder game, and drag onto each other to pair up. Everything the
 * old sidebar held lives in the side menu here, and Start goes to the courts.
 * You come back between rounds to change things.
 */

import { DndContext, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import type { DragEndEvent } from "@dnd-kit/core";
import { useState } from "react";
import { api } from "../api";
import { NameBox, groupColor } from "../components/NameBox";
import { SideMenu } from "../components/SideMenu";
import { withCandidate } from "../hooks/useSession";
import type { Session } from "../types";

interface Props {
  session: Session;
  error: string | null;
  busy: boolean;
  run: (
    action: () => Promise<Session>,
    options?: { optimistic?: (s: Session) => Session; blocking?: boolean },
  ) => Promise<Session | null>;
  onStart: () => void;
  onExit: () => void;
}

export function CheckInScreen({ session, error, busy, run, onStart, onExit }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);

  // A drag must not start from a plain tap, and the threshold has to clear the
  // long-press slop radius so the two gestures never both fire.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 12 } }),
  );

  const name = session.name;
  const checkedIn = session.candidates.filter((c) => c.checked_in);
  const perCourt = session.is_doubles ? 4 : 2;
  const courtsFilled = Math.floor(checkedIn.length / perCourt);
  const started = session.round_num > 0;

  function toggleCheckIn(playerName: string, isIn: boolean) {
    run(
      () => (isIn ? api.checkOut(name, playerName) : api.checkIn(name, playerName)),
      {
        optimistic: (s) =>
          withCandidate(s, playerName, {
            checked_in: !isIn,
            ...(isIn ? { challenging: false, group: null } : {}),
          }),
      },
    );
  }

  function longPress(playerName: string, isIn: boolean, challenging: boolean) {
    // Long press means "I'm in, and I want a hard game". On someone already in
    // it toggles the flag rather than checking them out.
    if (!isIn) {
      run(() => api.checkIn(name, playerName, true), {
        optimistic: (s) =>
          withCandidate(s, playerName, { checked_in: true, challenging: true }),
      });
    } else {
      run(() => api.setChallenge(name, playerName, !challenging), {
        optimistic: (s) => withCandidate(s, playerName, { challenging: !challenging }),
      });
    }
  }

  function onDragEnd(event: DragEndEvent) {
    const first = String(event.active.id);
    const second = event.over ? String(event.over.id) : null;
    if (!second || first === second) return;
    run(() => api.pair(name, first, second), { blocking: true });
  }

  return (
    <div className="app">
      <header className="topbar">
        <button className="btn btn-icon" onClick={onExit} aria-label="Leave session">
          ←
        </button>
        <h1>{session.name}</h1>
        <span className="count-pill">
          {checkedIn.length} in · {courtsFilled}{" "}
          {courtsFilled === 1 ? "court" : "courts"}
        </span>
        <button
          className="btn btn-icon"
          onClick={() => setMenuOpen(true)}
          aria-label="Open menu"
        >
          ☰
        </button>
      </header>

      <div className="content">
        {error && <div className="banner banner-error">{error}</div>}

        {!session.is_recorded && (
          <div className="banner banner-warn">
            This session is not being recorded to the dataset.
          </div>
        )}

        {session.queued_removals.length > 0 && (
          <div className="banner banner-warn">
            Leaving after this round: {session.queued_removals.join(", ")}
          </div>
        )}

        <p className="hint">
          Tap your name to check in. Press and hold to check in wanting a harder
          game. Drag one name onto another to play together.
        </p>

        <DndContext sensors={sensors} onDragEnd={onDragEnd}>
          <section className="section">
            <div className="name-grid">
              {session.candidates.map((candidate) => (
                <NameBox
                  key={candidate.name}
                  candidate={candidate}
                  onTap={() => toggleCheckIn(candidate.name, candidate.checked_in)}
                  onLongPress={() =>
                    longPress(
                      candidate.name,
                      candidate.checked_in,
                      candidate.challenging,
                    )
                  }
                />
              ))}
            </div>
            {session.candidates.length === 0 && (
              <p className="empty">Nobody on tonight's list yet. Add players from the menu.</p>
            )}
          </section>
        </DndContext>

        {session.groups.length > 0 && (
          <section className="section">
            <div className="section-head">
              <h2>Playing together</h2>
            </div>
            {session.groups.map((group) => (
              <div
                key={group.name}
                className="group-row"
                style={{ borderLeftColor: groupColor(group.name) }}
              >
                <span className="members">{group.members.join(" + ")}</span>
                <button
                  className="btn btn-icon btn-danger"
                  onClick={() =>
                    run(() => api.dissolveGroup(name, group.name), { blocking: true })
                  }
                  aria-label={`Break up ${group.members.join(" and ")}`}
                >
                  Break up
                </button>
              </div>
            ))}
          </section>
        )}

        <button
          className="btn btn-primary btn-lg"
          disabled={busy || checkedIn.length < perCourt}
          onClick={onStart}
        >
          {checkedIn.length < perCourt
            ? `Need ${perCourt - checkedIn.length} more to fill a court`
            : started
              ? "Back to the courts"
              : "Start playing"}
        </button>
      </div>

      {menuOpen && (
        <SideMenu
          session={session}
          run={run}
          busy={busy}
          onClose={() => setMenuOpen(false)}
          onExit={onExit}
        />
      )}
    </div>
  );
}
