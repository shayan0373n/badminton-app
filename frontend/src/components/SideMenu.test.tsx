/**
 * Side menu behaviour, with the API stubbed.
 *
 * Covers the guest form's skill field: an empty or out-of-range entry must
 * block the request rather than be sent as some other number.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SideMenu } from "./SideMenu";
import type { Session } from "../types";

vi.mock("../api", () => ({
  api: {
    addGuest: vi.fn(),
    listPlayers: vi.fn().mockResolvedValue({ players: [] }),
  },
}));

import { api } from "../api";

const SESSION: Session = {
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
};

function renderMenu() {
  const run = vi.fn(async (action: () => Promise<Session>) => action());
  render(
    <SideMenu session={SESSION} busy={false} run={run} onClose={vi.fn()} onExit={vi.fn()} />,
  );
  fireEvent.change(screen.getByLabelText("Guest name"), { target: { value: "Zoe" } });
  return {
    skill: screen.getByLabelText("Starting skill"),
    add: screen.getByRole("button", { name: "Add and check in" }),
  };
}

describe("SideMenu guest form", () => {
  beforeEach(() => {
    vi.mocked(api.addGuest).mockReset().mockResolvedValue(SESSION);
  });

  it("blocks adding a guest with an empty skill instead of sending 0", () => {
    const { skill, add } = renderMenu();

    fireEvent.change(skill, { target: { value: "" } });

    expect(add).toBeDisabled();
    expect(screen.getByText("Enter a skill from 0 to 60.")).toBeInTheDocument();
    fireEvent.click(add);
    expect(api.addGuest).not.toHaveBeenCalled();
  });

  it("blocks a skill outside the range the server accepts", () => {
    const { skill, add } = renderMenu();

    fireEvent.change(skill, { target: { value: "61" } });

    expect(add).toBeDisabled();
  });

  it("sends the entered skill as a number", async () => {
    const { skill, add } = renderMenu();

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
