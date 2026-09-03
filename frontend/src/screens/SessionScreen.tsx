/**
 * The playing screen.
 *
 * Deliberately bare: big name boxes, the games that still need a result, the
 * table, and a way back. Every management control lives on the check-in hub,
 * so there is nothing here to tap by mistake mid-game.
 */

import { useEffect, useState } from "react";
import { api } from "../api";
import type { Match, Session } from "../types";

interface Props {
  session: Session;
  error: string | null;
  busy: boolean;
  run: (
    action: () => Promise<Session>,
    options?: { optimistic?: (s: Session) => Session; blocking?: boolean },
  ) => Promise<Session | null>;
  onBack: () => void;
}

export function SessionScreen({ session, error, busy, run, onBack }: Props) {
  const lastIndex = session.rounds.length - 1;
  const [viewing, setViewing] = useState(lastIndex);

  // Follow along when a new round appears rather than stranding the user on an old one.
  useEffect(() => setViewing(session.rounds.length - 1), [session.rounds.length]);

  const index = Math.min(Math.max(viewing, 0), lastIndex);
  const round = session.rounds[index];
  const isLatest = index === lastIndex;

  if (!round) {
    return (
      <div className="app">
        <header className="topbar">
          <button className="btn btn-icon" onClick={onBack} aria-label="Back to check-in">
            ←
          </button>
          <h1>{session.name}</h1>
        </header>
        <div className="content">
          <p className="empty">No rounds yet.</p>
        </div>
      </div>
    );
  }

  const setWinner = (roundIndex: number, match: Match, side: 1 | 2) =>
    run(
      () =>
        api.setWinner(
          session.name,
          roundIndex,
          match.court,
          match.winner === side ? null : side,
        ),
      { blocking: false },
    );

  // Games from any other round that never got a result, newest first, so the
  // organizer can catch up without navigating away.
  const unentered = session.rounds
    .flatMap((r, i) =>
      i === index
        ? []
        : r.matches.filter((m) => m.winner === null).map((m) => ({ roundIndex: i, round: r, match: m })),
    )
    .reverse();

  return (
    <div className="app">
      <header className="topbar">
        <button className="btn btn-icon" onClick={onBack} aria-label="Back to check-in">
          ←
        </button>
        <h1>{session.name}</h1>
        <span className="sub">
          Round {round.round_num} of {session.round_num}
        </span>
      </header>

      <div className="content">
        {error && <div className="banner banner-error">{error}</div>}

        <div className="row" style={{ marginBottom: 14 }}>
          <button
            className="btn"
            disabled={index === 0}
            onClick={() => setViewing(index - 1)}
            aria-label="Previous round"
          >
            ◀ Previous
          </button>
          {isLatest ? (
            <button
              className="btn btn-primary"
              disabled={busy}
              onClick={() => run(() => api.nextRound(session.name), { blocking: true })}
            >
              {busy ? "Generating round…" : "Next round ▶"}
            </button>
          ) : (
            <button
              className="btn"
              onClick={() => setViewing(index + 1)}
              aria-label="Next round"
            >
              Next ▶
            </button>
          )}
        </div>

        {round.resting.length > 0 && (
          <p className="resting">
            <b>Resting:</b> {round.resting.join(", ")}
          </p>
        )}

        <div className="courts">
          {round.matches.map((match) => (
            <CourtCard
              key={match.court}
              match={match}
              onPick={(side) => setWinner(index, match, side)}
            />
          ))}
        </div>

        {round.matches.length === 0 && (
          <p className="empty">
            No courts could be formed with the players currently checked in.
          </p>
        )}

        {unentered.length > 0 && (
          <section className="section" style={{ marginTop: 26 }}>
            <div className="section-head">
              <h2>Awaiting results</h2>
            </div>
            <div className="courts">
              {unentered.map(({ roundIndex, round: r, match }) => (
                <CourtCard
                  key={`${roundIndex}-${match.court}`}
                  match={match}
                  label={`Round ${r.round_num} · Court ${match.court}`}
                  onPick={(side) => setWinner(roundIndex, match, side)}
                />
              ))}
            </div>
          </section>
        )}

        <section className="section" style={{ marginTop: 26 }}>
          <div className="section-head">
            <h2>Standings</h2>
          </div>
          <table className="standings">
            <thead>
              <tr>
                <th>Player</th>
                <th className="num">Played</th>
                <th className="num">Won</th>
                <th className="num">Rate</th>
              </tr>
            </thead>
            <tbody>
              {session.standings.map((s) => (
                <tr key={s.name}>
                  <td>{s.name}</td>
                  <td className="num">{s.matches}</td>
                  <td className="num">{s.wins}</td>
                  <td className="num">
                    {s.matches ? `${Math.round(s.ratio * 100)}%` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}

function CourtCard({
  match,
  onPick,
  label,
}: {
  match: Match;
  onPick: (side: 1 | 2) => void;
  label?: string;
}) {
  return (
    <div className="court">
      <div className="court-head">
        <span>{label ?? `Court ${match.court}`}</span>
        {match.winner === null && <span>Tap the winning side</span>}
      </div>
      <Side
        players={match.team_1}
        locked={match.locked_1}
        won={match.winner === 1}
        onPick={() => onPick(1)}
      />
      <div className="versus">vs</div>
      <Side
        players={match.team_2}
        locked={match.locked_2}
        won={match.winner === 2}
        onPick={() => onPick(2)}
      />
    </div>
  );
}

function Side({
  players,
  locked,
  won,
  onPick,
}: {
  players: string[];
  locked: boolean;
  won: boolean;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      className={won ? "side won" : "side"}
      onClick={onPick}
      aria-pressed={won}
      aria-label={`${players.join(" and ")}${won ? ", winners" : ""}`}
    >
      {players.map((player) => (
        <span className="player" key={player}>
          {player}
        </span>
      ))}
      {locked && <span className="lock">Paired</span>}
    </button>
  );
}
