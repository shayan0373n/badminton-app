/**
 * Session state for the whole app.
 *
 * Every mutation returns the full snapshot, so there is no cache to invalidate
 * and no partial update to reconcile: send, then replace. `apply` lets a caller
 * paint the expected result first so a tap never waits for the network, and the
 * server's answer overwrites it a moment later.
 */

import { useCallback, useRef, useState } from "react";
import { ApiError } from "../api";
import type { Session } from "../types";

export function useSession(initial: Session | null = null) {
  const [session, setSession] = useState<Session | null>(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Late responses from superseded requests must not overwrite newer state.
  const generation = useRef(0);

  const run = useCallback(
    async (
      action: () => Promise<Session>,
      options: { optimistic?: (current: Session) => Session; blocking?: boolean } = {},
    ) => {
      const mine = ++generation.current;
      const previous = session;

      if (options.optimistic && previous) {
        setSession(options.optimistic(previous));
      }
      if (options.blocking) setBusy(true);
      setError(null);

      try {
        const next = await action();
        if (generation.current === mine) setSession(next);
        return next;
      } catch (e) {
        // Roll the optimistic paint back so the screen matches the server again.
        if (generation.current === mine && options.optimistic && previous) {
          setSession(previous);
        }
        setError(e instanceof ApiError ? e.message : "Something went wrong.");
        return null;
      } finally {
        if (options.blocking) setBusy(false);
      }
    },
    [session],
  );

  return { session, setSession, error, setError, busy, run };
}

/** Returns a copy of the snapshot with one candidate changed. */
export function withCandidate(
  session: Session,
  name: string,
  changes: Partial<Session["candidates"][number]>,
): Session {
  return {
    ...session,
    candidates: session.candidates.map((c) =>
      c.name === name ? { ...c, ...changes } : c,
    ),
  };
}
