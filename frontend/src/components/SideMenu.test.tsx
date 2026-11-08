/**
 * Upload-results behaviour in the session drawer, with the API stubbed.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SideMenu } from "./SideMenu";
import type { Session } from "../types";

vi.mock("../api", () => ({
  api: {
    submit: vi.fn(),
    getSession: vi.fn(),
    listPlayers: vi.fn().mockResolvedValue({ players: [] }),
  },
}));

import { api } from "../api";

const playedRound = {
  round_num: 1,
  resting: [],
  matches: [
    { court: 1, team_1: ["A", "B"], team_2: ["C", "D"], locked_1: false, locked_2: false, winner: 1 as const },
  ],
};

function makeSession(overrides: Partial<Session> = {}): Session {
  return {
    name: "Night",
    is_doubles: true,
    is_recorded: true,
    num_courts: 1,
    weights: { skill: 1, power: 1, pairing: 1 },
    round_num: 1,
    results_dirty: true,
    candidates: [],
    groups: [],
    rounds: [playedRound],
    standings: [],
    ...overrides,
  };
}

/** Renders the drawer with a run stub that calls the action, like useSession does. */
function renderMenu(session = makeSession()) {
  const run = vi.fn(async (action: () => Promise<Session>) => {
    try {
      return await action();
    } catch {
      return null;
    }
  });
  render(
    <SideMenu session={session} busy={false} run={run} onClose={vi.fn()} onExit={vi.fn()} />,
  );
  return { run };
}

describe("SideMenu upload", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows Uploading… while the request is in flight", async () => {
    let resolve!: (v: unknown) => void;
    vi.mocked(api.submit).mockReturnValue(new Promise((r) => (resolve = r)) as never);
    renderMenu();

    fireEvent.click(screen.getByRole("button", { name: "Upload results" }));
    expect(await screen.findByRole("button", { name: "Uploading…" })).toBeInTheDocument();

    resolve({ recorded: 1, unreported: 0, session: makeSession({ results_dirty: false }) });
    expect(await screen.findByRole("button", { name: "Upload results" })).toBeInTheDocument();
  });

  it("reports the outcome beside the button and reuses the returned session", async () => {
    vi.mocked(api.submit).mockResolvedValue({
      recorded: 3,
      unreported: 1,
      session: makeSession({ results_dirty: false }),
    });
    const { run } = renderMenu();

    fireEvent.click(screen.getByRole("button", { name: "Upload results" }));

    expect(await screen.findByText("Uploaded 3 matches · 1 without a winner")).toBeInTheDocument();
    expect(run).toHaveBeenCalledTimes(1);
    expect(api.getSession).not.toHaveBeenCalled();
  });

  it("shows the failure beside the button", async () => {
    vi.mocked(api.submit).mockRejectedValue(new Error("Database unreachable"));
    renderMenu();

    fireEvent.click(screen.getByRole("button", { name: "Upload results" }));

    expect(await screen.findByText("Database unreachable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload results" })).toBeEnabled();
  });

  it("shows Uploaded ✓ when reported results are already uploaded", () => {
    renderMenu(makeSession({ results_dirty: false }));
    expect(screen.getByText("Uploaded ✓")).toBeInTheDocument();
  });

  it("says nothing about upload state before any result is reported", () => {
    renderMenu(makeSession({ results_dirty: false, rounds: [] }));
    expect(screen.queryByText("Uploaded ✓")).not.toBeInTheDocument();
    expect(screen.queryByText("Not uploaded yet.")).not.toBeInTheDocument();
  });
});
