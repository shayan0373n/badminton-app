/**
 * Typed client for the badminton API.
 *
 * Every mutation returns the whole session snapshot, so callers replace their
 * state with the response rather than patching it. That keeps the client from
 * ever recomputing something the server already derived.
 */

import type {
  RegistryPlayer,
  Session,
  SessionSummary,
  SubmitResult,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
      ...init,
    });
  } catch {
    throw new ApiError("Can't reach the server. Check the connection.", 0);
  }

  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(detailOf(body) ?? `Request failed (${response.status})`, response.status);
  }
  return body as T;
}

/** Pulls a readable message out of FastAPI's error shapes. */
function detailOf(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    if (first?.msg) return first.msg;
  }
  return null;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
});

export const api = {
  listPlayers: () => request<{ players: RegistryPlayer[] }>("/players"),

  savePlayers: (players: Pick<RegistryPlayer, "name" | "gender" | "prior_mu">[]) =>
    request<{ saved: number }>("/players", { ...json({ players }), method: "PUT" }),

  listSessions: () => request<{ sessions: SessionSummary[] }>("/sessions"),

  createSession: (body: {
    name: string;
    candidates: string[];
    num_courts: number;
    is_doubles: boolean;
    is_recorded: boolean;
  }) => request<Session>("/sessions", json(body)),

  getSession: (name: string) => request<Session>(`/sessions/${enc(name)}`),

  deleteSession: (name: string) =>
    request<void>(`/sessions/${enc(name)}`, { method: "DELETE" }),

  updateSettings: (
    name: string,
    body: { num_courts?: number; weights?: Record<string, number> },
  ) =>
    request<Session>(`/sessions/${enc(name)}`, {
      ...json(body),
      method: "PATCH",
    }),

  checkIn: (name: string, player: string, wantsChallenge = false) =>
    request<Session>(
      `/sessions/${enc(name)}/checkin/${enc(player)}`,
      json({ wants_challenge: wantsChallenge }),
    ),

  checkOut: (name: string, player: string) =>
    request<Session>(`/sessions/${enc(name)}/checkin/${enc(player)}`, {
      method: "DELETE",
    }),

  setChallenge: (name: string, player: string, wantsChallenge: boolean) =>
    request<Session>(
      `/sessions/${enc(name)}/challenge/${enc(player)}`,
      json({ wants_challenge: wantsChallenge }),
    ),

  pair: (name: string, first: string, second: string) =>
    request<Session>(`/sessions/${enc(name)}/groups`, json({ first, second })),

  dissolveGroup: (name: string, group: string) =>
    request<Session>(`/sessions/${enc(name)}/groups/${enc(group)}`, {
      method: "DELETE",
    }),

  unpair: (name: string, player: string) =>
    request<Session>(`/sessions/${enc(name)}/groups/members/${enc(player)}`, {
      method: "DELETE",
    }),

  addCandidate: (name: string, player: string) =>
    request<Session>(`/sessions/${enc(name)}/candidates/${enc(player)}`, {
      method: "POST",
    }),

  removeCandidate: (name: string, player: string) =>
    request<Session>(`/sessions/${enc(name)}/candidates/${enc(player)}`, {
      method: "DELETE",
    }),

  addGuest: (name: string, body: { name: string; gender: "M" | "F"; mu: number }) =>
    request<Session>(`/sessions/${enc(name)}/players`, json(body)),

  nextRound: (name: string) =>
    request<Session>(`/sessions/${enc(name)}/rounds`, { method: "POST" }),

  setWinner: (name: string, roundIndex: number, court: number, winner: 1 | 2 | null) =>
    request<Session>(
      `/sessions/${enc(name)}/rounds/${roundIndex}/courts/${court}`,
      { ...json({ winner }), method: "PUT" },
    ),

  submit: (name: string) =>
    request<SubmitResult>(`/sessions/${enc(name)}/submit`, { method: "POST" }),
};

const enc = encodeURIComponent;
