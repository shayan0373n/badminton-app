/**
 * The playing screen: reading the courts, tapping winners, and getting back.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionScreen } from "./SessionScreen";
import type { Session } from "../types";

vi.mock("../api", () => ({
  api: { setWinner: vi.fn(), nextRound: vi.fn() },
}));

import { api } from "../api";

function makeSession(overrides: Partial<Session> = {}): Session {
  return {
    name: "Night",
    is_doubles: true,
    is_recorded: true,
    num_courts: 2,
    weights: { skill: 1, power: 1, pairing: 1 },
    round_num: 2,
    results_dirty: false,
    queued_removals: [],
    candidates: [],
    groups: [],
    rounds: [
      {
        round_num: 1,
        resting: ["Zoe"],
        matches: [
          {
            court: 1,
            team_1: ["Alice", "Bob"],
            team_2: ["Cara", "Dan"],
            locked_1: false,
            locked_2: false,
            winner: null,
          },
        ],
      },
      {
        round_num: 2,
        resting: [],
        matches: [
          {
            court: 1,
            team_1: ["Alice", "Cara"],
            team_2: ["Bob", "Dan"],
            locked_1: true,
            locked_2: false,
            winner: 1,
          },
        ],
      },
    ],
    standings: [
      { name: "Alice", matches: 1, wins: 1, ratio: 1 },
      { name: "Bob", matches: 1, wins: 0, ratio: 0 },
    ],
    ...overrides,
  };
}

function renderScreen(session = makeSession(), busy = false) {
  const run = vi.fn(async (action: () => Promise<Session>) => action());
  const onBack = vi.fn();
  render(
    <SessionScreen
      session={session}
      error={null}
      busy={busy}
      run={run}
      onBack={onBack}
    />,
  );
  return { run, onBack };
}

describe("SessionScreen", () => {
  beforeEach(() => vi.clearAllMocks());

  it("opens on the latest round", () => {
    renderScreen();
    expect(screen.getByText("Round 2 of 2")).toBeInTheDocument();
  });

  it("shows both sides of each court", () => {
    renderScreen();
    expect(screen.getByRole("button", { name: /Alice and Cara/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Bob and Dan/ })).toBeInTheDocument();
  });

  it("marks the winning side", () => {
    renderScreen();
    expect(screen.getByRole("button", { name: /Alice and Cara, winners/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("marks a paired team with a lock", () => {
    renderScreen();
    expect(screen.getByText(/Paired/)).toBeInTheDocument();
  });

  it("records a winner when a side is tapped", async () => {
    renderScreen();
    fireEvent.click(screen.getByRole("button", { name: /Bob and Dan/ }));

    await waitFor(() => expect(api.setWinner).toHaveBeenCalledWith("Night", 1, 1, 2));
  });

  it("clears the winner when the winning side is tapped again", async () => {
    renderScreen();
    fireEvent.click(screen.getByRole("button", { name: /Alice and Cara, winners/ }));

    await waitFor(() => expect(api.setWinner).toHaveBeenCalledWith("Night", 1, 1, null));
  });

  it("navigates back through rounds", () => {
    renderScreen();
    fireEvent.click(screen.getByRole("button", { name: /Previous round/ }));

    expect(screen.getByText("Round 1 of 2")).toBeInTheDocument();
    expect(screen.getByText(/Resting:/).parentElement).toHaveTextContent("Resting: Zoe");
  });

  it("generates the next round only from the latest one", async () => {
    renderScreen();
    fireEvent.click(screen.getByRole("button", { name: /Next round/ }));

    await waitFor(() => expect(api.nextRound).toHaveBeenCalledWith("Night"));
  });

  it("says what it is doing while the solver runs", () => {
    renderScreen(makeSession(), true);
    expect(screen.getByText(/Generating round/)).toBeInTheDocument();
  });

  it("collects games from other rounds that still need a result", () => {
    renderScreen();
    const section = screen.getByText("Awaiting results").closest("section")!;
    expect(within(section).getByText("Round 1 · Court 1")).toBeInTheDocument();
  });

  it("records a result for a game from an earlier round", async () => {
    renderScreen();
    const section = screen.getByText("Awaiting results").closest("section")!;
    fireEvent.click(within(section).getByRole("button", { name: /Alice and Bob/ }));

    // Round index 0, not the round on screen.
    await waitFor(() => expect(api.setWinner).toHaveBeenCalledWith("Night", 0, 1, 1));
  });

  it("shows tonight's standings", () => {
    renderScreen();
    const table = screen.getByRole("table");
    expect(within(table).getByText("Alice")).toBeInTheDocument();
    expect(within(table).getByText("100%")).toBeInTheDocument();
    expect(within(table).getByText("0%")).toBeInTheDocument();
  });

  it("goes back to the hub", () => {
    const { onBack } = renderScreen();
    fireEvent.click(screen.getByRole("button", { name: /Back to check-in/ }));
    expect(onBack).toHaveBeenCalled();
  });

  it("copes with a session that has no rounds yet", () => {
    renderScreen(makeSession({ rounds: [], round_num: 0 }));
    expect(screen.getByText("No rounds yet.")).toBeInTheDocument();
  });
});
