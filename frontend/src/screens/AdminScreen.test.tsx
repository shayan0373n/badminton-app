/**
 * The admin page: the rating table's ordering and the recalculate button.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AdminScreen } from "./AdminScreen";
import type { RegistryPlayer } from "../types";

vi.mock("../api", () => ({
  api: { listPlayers: vi.fn(), recalculateRatings: vi.fn() },
}));

import { api } from "../api";

const PLAYERS: RegistryPlayer[] = [
  { name: "Bob", gender: "M", prior_mu: 25, mu: 24, sigma: 2, rating: 18 },
  { name: "Alice", gender: "F", prior_mu: 25, mu: 28, sigma: 1, rating: 25 },
  { name: "Zoe", gender: "F", prior_mu: 25, mu: null, sigma: null, rating: null },
];

function names(): string[] {
  return screen
    .getAllByRole("row")
    .slice(1)
    .map((row) => row.querySelectorAll("td")[1].textContent);
}

describe("AdminScreen", () => {
  beforeEach(() => {
    vi.mocked(api.listPlayers).mockReset().mockResolvedValue({ players: PLAYERS });
    vi.mocked(api.recalculateRatings).mockReset();
  });

  it("ranks by mu with unrated players last", async () => {
    render(<AdminScreen />);
    await waitFor(() => expect(names()).toEqual(["Alice", "Bob", "Zoe"]));
  });

  it("clicking a header sorts by it, and again reverses it", async () => {
    render(<AdminScreen />);
    await screen.findByText("Alice");

    fireEvent.click(screen.getByRole("button", { name: "Player" }));
    expect(names()).toEqual(["Alice", "Bob", "Zoe"]);

    fireEvent.click(screen.getByRole("button", { name: /Player/ }));
    expect(names()).toEqual(["Zoe", "Bob", "Alice"]);

    fireEvent.click(screen.getByRole("button", { name: /^σ/ }));
    expect(names()).toEqual(["Bob", "Alice", "Zoe"]);
  });

  it("recalculating shows progress, then reports the counts and reloads the table", async () => {
    let finish!: (value: { players: number; matches: number }) => void;
    vi.mocked(api.recalculateRatings).mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    render(<AdminScreen />);
    await screen.findByText("Alice");

    fireEvent.click(screen.getByRole("button", { name: "Recalculate ratings" }));

    const running = await screen.findByRole("button", { name: "Recalculating…" });
    expect(running).toBeDisabled();

    finish({ players: 3, matches: 40 });

    await screen.findByText(/3 players from 40 matches/);
    expect(screen.getByRole("button", { name: "Recalculate ratings" })).toBeEnabled();
    expect(api.listPlayers).toHaveBeenCalledTimes(2);
  });
});
