/**
 * Shapes returned by the API.
 *
 * Written by hand rather than generated: the surface is small, and one file
 * is easier to keep honest than a codegen step nobody remembers to run.
 * These mirror `session_service.build_session_snapshot`.
 */

export interface Candidate {
  name: string;
  gender: "M" | "F";
  checked_in: boolean;
  challenging: boolean;
  group: string | null;
}

export interface Group {
  name: string;
  members: string[];
}

export interface Match {
  court: number;
  team_1: string[];
  team_2: string[];
  locked_1: boolean;
  locked_2: boolean;
  winner: 1 | 2 | null;
}

export interface Round {
  round_num: number;
  resting: string[];
  matches: Match[];
}

export interface Standing {
  name: string;
  matches: number;
  wins: number;
  ratio: number;
}

export interface Session {
  name: string;
  is_doubles: boolean;
  is_recorded: boolean;
  num_courts: number;
  weights: Record<string, number>;
  round_num: number;
  results_dirty: boolean;
  queued_removals: string[];
  candidates: Candidate[];
  groups: Group[];
  rounds: Round[];
  standings: Standing[];
}

export interface SessionSummary {
  name: string;
  round_num: number;
  checked_in: number;
  candidates: number;
  is_doubles: boolean;
  is_recorded: boolean;
}

export interface RegistryPlayer {
  name: string;
  gender: "M" | "F";
  prior_mu: number;
  mu: number | null;
  sigma: number | null;
  rating: number | null;
}

export interface SubmitResult {
  recorded: number;
  unreported: number;
  session: Session;
}
