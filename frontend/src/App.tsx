/**
 * Screen routing.
 *
 * Three screens, one piece of state. Setup opens a session; the hub and the
 * courts swap back and forth, which is the whole navigation model: manage on
 * the hub, play on the courts.
 */

import { useState } from "react";
import { api } from "./api";
import { CheckInScreen } from "./screens/CheckInScreen";
import { SessionScreen } from "./screens/SessionScreen";
import { SetupScreen } from "./screens/SetupScreen";
import { useSession } from "./hooks/useSession";
import type { Session } from "./types";

type Screen = "setup" | "checkin" | "playing";

export default function App() {
  const [screen, setScreen] = useState<Screen>("setup");
  const { session, setSession, error, setError, busy, run } = useSession();

  function open(next: Session) {
    setSession(next);
    setError(null);
    // Resuming a night that already has rounds should land on the courts.
    setScreen(next.round_num > 0 ? "playing" : "checkin");
  }

  function exit() {
    setSession(null);
    setError(null);
    setScreen("setup");
  }

  async function start() {
    if (!session) return;
    // Start means "go and play". It only generates a round when there isn't one,
    // so coming back to change something never disturbs the round in progress.
    if (session.round_num === 0) {
      const next = await run(() => api.nextRound(session.name), { blocking: true });
      if (!next) return;
    }
    setScreen("playing");
  }

  if (screen === "setup" || !session) {
    return <SetupScreen onOpen={open} />;
  }

  if (screen === "playing") {
    return (
      <SessionScreen
        session={session}
        error={error}
        busy={busy}
        run={run}
        onBack={() => setScreen("checkin")}
      />
    );
  }

  return (
    <CheckInScreen
      session={session}
      error={error}
      busy={busy}
      run={run}
      onStart={start}
      onExit={exit}
    />
  );
}
