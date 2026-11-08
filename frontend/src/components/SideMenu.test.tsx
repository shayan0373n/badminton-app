/**
 * Side menu behaviour, with the API stubbed.
 *
 * Covers the guest form's skill field (an empty or out-of-range entry must
 * block the request rather than be sent as some other number), the weights
 * shown, and the upload-results button's progress and outcome.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SideMenu } from "./SideMenu";
import type { Session } from "../types";

vi.mock("../api", () => ({
  api: {
    addGuest: vi.fn(),
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
    num_courts: 2,
    weights: { skill: 1, power: 1.5, pairing: 1 },
    round_num: 0,
    results_dirty: false,
    candidates: [],
    groups: [],
    rounds: [],
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

/** Renders the drawer with a guest name typed in and returns the guest form's controls. */
function renderGuestForm() {
  renderMenu();
  fireEvent.change(screen.getByLabelText("Guest name"), { target: { value: "Zoe" } });
  return {
    skill: screen.getByLabelText("Starting skill"),
    add: screen.getByRole("button", { name: "Add and check in" }),
  };
}

describe("SideMenu guest form", () => {
  beforeEach(() => {
    vi.mocked(api.addGuest).mockReset().mockResolvedValue(makeSession());
  });

  it("blocks adding a guest with an empty skill instead of sending 0", () => {
    const { skill, add } = renderGuestForm();

    fireEvent.change(skill, { target: { value: "" } });

    expect(add).toBeDisabled();
    expect(screen.getByText("Enter a skill from 0 to 60.")).toBeInTheDocument();
    fireEvent.click(add);
    expect(api.addGuest).not.toHaveBeenCalled();
  });

  it("blocks a skill outside the range the server accepts", () => {
    const { skill, add } = renderGuestForm();

    fireEvent.change(skill, { target: { value: "61" } });

    expect(add).toBeDisabled();
  });

  it("sends the entered skill as a number", async () => {
    const { skill, add } = renderGuestForm();

    fireEvent.change(skill, { target: { value: "30" } });
    fireEvent.click(add);

    await waitFor(() =>
      expect(api.addGuest).toHaveBeenCalledWith("Night", { name: "Zoe", gender: "M", mu: 30 }),
    );
  });
});

describe("SideMenu weights", () => {
  it("shows the session's own weights", () => {
    renderMenu();

    expect(screen.getByText("1.5")).toBeInTheDocument();
  });
});

describe("SideMenu upload", () => {
  const played = (overrides: Partial<Session> = {}) =>
    makeSession({ round_num: 1, rounds: [playedRound], results_dirty: true, ...overrides });

  beforeEach(() => vi.clearAllMocks());

  it("shows Uploading… while the request is in flight", async () => {
    let resolve!: (v: unknown) => void;
    vi.mocked(api.submit).mockReturnValue(new Promise((r) => (resolve = r)) as never);
    renderMenu(played());

    fireEvent.click(screen.getByRole("button", { name: "Upload results" }));
    expect(await screen.findByRole("button", { name: "Uploading…" })).toBeInTheDocument();

    resolve({ recorded: 1, unreported: 0, session: played({ results_dirty: false }) });
    expect(await screen.findByRole("button", { name: "Upload results" })).toBeInTheDocument();
  });

  it("reports the outcome beside the button and reuses the returned session", async () => {
    vi.mocked(api.submit).mockResolvedValue({
      recorded: 3,
      unreported: 1,
      session: played({ results_dirty: false }),
    });
    const { run } = renderMenu(played());

    fireEvent.click(screen.getByRole("button", { name: "Upload results" }));

    expect(await screen.findByText("Uploaded 3 matches · 1 without a winner")).toBeInTheDocument();
    expect(run).toHaveBeenCalledTimes(1);
    expect(api.getSession).not.toHaveBeenCalled();
  });

  it("shows the failure beside the button", async () => {
    vi.mocked(api.submit).mockRejectedValue(new Error("Database unreachable"));
    renderMenu(played());

    fireEvent.click(screen.getByRole("button", { name: "Upload results" }));

    expect(await screen.findByText("Database unreachable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload results" })).toBeEnabled();
  });

  it("shows Uploaded ✓ when reported results are already uploaded", () => {
    renderMenu(played({ results_dirty: false }));
    expect(screen.getByText("Uploaded ✓")).toBeInTheDocument();
  });

  it("says nothing about upload state before any result is reported", () => {
    renderMenu();
    expect(screen.queryByText("Uploaded ✓")).not.toBeInTheDocument();
    expect(screen.queryByText("Not uploaded yet.")).not.toBeInTheDocument();
  });
});
