/**
 * Check-in hub behaviour, with the API stubbed.
 *
 * These cover the wiring the user actually feels: which call a tap makes, which
 * a long press makes, and that the screen paints the result before the network
 * answers.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CheckInScreen } from "./CheckInScreen";
import { LONG_PRESS_MS } from "../hooks/useLongPress";
import type { Session } from "../types";

vi.mock("../api", () => ({
  api: {
    checkIn: vi.fn(),
    checkOut: vi.fn(),
    setChallenge: vi.fn(),
    pair: vi.fn(),
    dissolveGroup: vi.fn(),
    listPlayers: vi.fn().mockResolvedValue({ players: [] }),
  },
}));

import { api } from "../api";

function makeSession(overrides: Partial<Session> = {}): Session {
  return {
    name: "Night",
    is_doubles: true,
    is_recorded: true,
    num_courts: 2,
    weights: { skill: 1, power: 1, pairing: 1 },
    round_num: 0,
    results_dirty: false,
    queued_removals: [],
    candidates: [
      { name: "Alice", gender: "F", checked_in: false, challenging: false, groups: [] },
      { name: "Bob", gender: "M", checked_in: true, challenging: false, groups: [] },
      { name: "Cara", gender: "F", checked_in: true, challenging: true, groups: [] },
      { name: "Dan", gender: "M", checked_in: true, challenging: false, groups: ["G1"] },
    ],
    groups: [{ name: "G1", members: ["Dan", "Eve"] }],
    rounds: [],
    standings: [],
    ...overrides,
  };
}

function renderScreen(session = makeSession()) {
  const run = vi.fn(async (action: () => Promise<Session>) => action());
  const onStart = vi.fn();
  const onExit = vi.fn();
  render(
    <CheckInScreen
      session={session}
      error={null}
      busy={false}
      run={run}
      onStart={onStart}
      onExit={onExit}
    />,
  );
  return { run, onStart, onExit };
}

const box = (name: string) =>
  screen.getByRole("button", { name: new RegExp(`^${name},`) });

const press = (el: Element) => fireEvent.pointerDown(el, { button: 0, clientX: 0, clientY: 0 });

describe("CheckInScreen", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows who is in and who is not", () => {
    renderScreen();

    expect(box("Alice")).toHaveAttribute("aria-pressed", "false");
    expect(box("Bob")).toHaveAttribute("aria-pressed", "true");
  });

  it("announces challenge and group state to screen readers", () => {
    renderScreen();

    expect(box("Cara")).toHaveAccessibleName(/wants a stronger match/);
    expect(box("Dan")).toHaveAccessibleName(/paired: G1/);
  });

  it("checks a player in when tapped", async () => {
    renderScreen();

    press(box("Alice"));
    fireEvent.pointerUp(box("Alice"));

    await waitFor(() => expect(api.checkIn).toHaveBeenCalledWith("Night", "Alice"));
    expect(api.checkOut).not.toHaveBeenCalled();
  });

  it("checks a player out when tapped again", async () => {
    renderScreen();

    press(box("Bob"));
    fireEvent.pointerUp(box("Bob"));

    await waitFor(() => expect(api.checkOut).toHaveBeenCalledWith("Night", "Bob"));
  });

  it("long press on an absent player checks them in wanting a challenge", async () => {
    vi.useFakeTimers();
    renderScreen();

    press(box("Alice"));
    await vi.advanceTimersByTimeAsync(LONG_PRESS_MS);
    vi.useRealTimers();

    await waitFor(() =>
      expect(api.checkIn).toHaveBeenCalledWith("Night", "Alice", true),
    );
  });

  it("long press on someone already in toggles their challenge flag", async () => {
    vi.useFakeTimers();
    renderScreen();

    press(box("Bob"));
    await vi.advanceTimersByTimeAsync(LONG_PRESS_MS);
    vi.useRealTimers();

    await waitFor(() =>
      expect(api.setChallenge).toHaveBeenCalledWith("Night", "Bob", true),
    );
    expect(api.checkIn).not.toHaveBeenCalled();
  });

  it("long press clears an existing challenge", async () => {
    vi.useFakeTimers();
    renderScreen();

    press(box("Cara"));
    await vi.advanceTimersByTimeAsync(LONG_PRESS_MS);
    vi.useRealTimers();

    await waitFor(() =>
      expect(api.setChallenge).toHaveBeenCalledWith("Night", "Cara", false),
    );
  });

  it("paints the check-in before the request resolves", async () => {
    const session = makeSession();
    const run = vi.fn();
    render(
      <CheckInScreen
        session={session}
        error={null}
        busy={false}
        run={run}
        onStart={vi.fn()}
        onExit={vi.fn()}
      />,
    );

    press(box("Alice"));
    fireEvent.pointerUp(box("Alice"));

    const [, options] = run.mock.calls[0];
    const painted = options.optimistic(session);
    expect(painted.candidates.find((c: { name: string }) => c.name === "Alice")).toMatchObject({
      checked_in: true,
    });
  });

  it("counts how many courts the turnout fills", () => {
    renderScreen();
    // Three checked in, doubles: not enough for a court yet.
    expect(screen.getByText(/3 checked in · 0 courts/)).toBeInTheDocument();
  });

  it("blocks Start until a court can be filled", () => {
    renderScreen();
    expect(
      screen.getByRole("button", { name: /1 more for a court/ }),
    ).toBeDisabled();
  });

  it("enables Start once there are enough players", () => {
    const session = makeSession({
      candidates: ["A", "B", "C", "D"].map((name) => ({
        name,
        gender: "M" as const,
        checked_in: true,
        challenging: false,
        groups: [],
      })),
      groups: [],
    });
    const { onStart } = renderScreen(session);

    const start = screen.getByRole("button", { name: /Start playing/ });
    expect(start).toBeEnabled();
    fireEvent.click(start);
    expect(onStart).toHaveBeenCalled();
  });

  it("says 'back to the courts' once the night has started", () => {
    const session = makeSession({
      round_num: 2,
      candidates: ["A", "B", "C", "D"].map((name) => ({
        name,
        gender: "M" as const,
        checked_in: true,
        challenging: false,
        groups: [],
      })),
      groups: [],
    });
    renderScreen(session);

    expect(screen.getByRole("button", { name: /Back to courts/ })).toBeEnabled();
  });

  it("lists groups and can break them up", async () => {
    renderScreen();

    expect(screen.getByText("Dan + Eve")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Unpair Dan and Eve/ }));

    await waitFor(() => expect(api.dissolveGroup).toHaveBeenCalledWith("Night", "G1"));
  });

  it("warns about players leaving after the round", () => {
    renderScreen(makeSession({ queued_removals: ["Bob"] }));
    expect(screen.getByText(/Leaving after this round: Bob/)).toBeInTheDocument();
  });

  it("warns when the session is not counting toward ratings", () => {
    renderScreen(makeSession({ is_recorded: false }));
    expect(screen.getByText(/Not recorded to ratings/)).toBeInTheDocument();
  });
});
