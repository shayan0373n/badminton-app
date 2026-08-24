-- =============================================================================
-- Badminton App Database Schema
-- =============================================================================
-- This schema defines the core tables for the Badminton App.
-- Run this script against your Supabase PostgreSQL database to initialize.
--
-- Default values for prior_mu and prior_sigma should match constants.py:
--   TTT_DEFAULT_MU = 25.0 (TTT_MU_AVERAGE)
--   TTT_DEFAULT_SIGMA = 6.0
-- =============================================================================

-- players table
-- Note: gender is stored as text ('M' or 'F') to match Python Gender enum values
CREATE TABLE IF NOT EXISTS public.players (
  id serial PRIMARY KEY,
  name text NOT NULL UNIQUE,
  gender text CHECK (gender IN ('M', 'F')),
  prior_mu double precision DEFAULT 25.0,
  prior_sigma double precision DEFAULT 6.0,
  mu double precision,
  sigma double precision,
  created_at timestamptz DEFAULT now()
);

-- seasons table
-- A season is a date window. Sessions belong to a season implicitly via their
-- created_at timestamp (no season_id FK). The open/current season is the single
-- row with end_date IS NULL; live ratings process only sessions on or after its
-- start_date. Closed seasons keep end_date for record-keeping / historical recompute.
CREATE TABLE IF NOT EXISTS public.seasons (
  id serial PRIMARY KEY,
  start_date timestamptz NOT NULL,
  end_date timestamptz,
  created_at timestamptz DEFAULT now()
);

-- At most one open season at a time.
CREATE UNIQUE INDEX IF NOT EXISTS one_open_season
  ON public.seasons ((end_date IS NULL)) WHERE end_date IS NULL;

-- sessions table
CREATE TABLE IF NOT EXISTS public.sessions (
  id serial PRIMARY KEY,
  name text NOT NULL,
  game_mode text CHECK (game_mode IN ('Singles', 'Doubles')),
  created_at timestamptz DEFAULT now()
);

-- matches table
-- Semantics:
--   Singles: player_1 vs player_2 (player_3/4 are NULL)
--   Doubles: Team 1 (player_1, player_2) vs Team 2 (player_3, player_4)
-- winner_side: 1 = player_1 (or Team 1) won, 2 = player_2 (or Team 2) won
CREATE TABLE IF NOT EXISTS public.matches (
  id serial PRIMARY KEY,
  session_id int NOT NULL REFERENCES public.sessions(id),
  player_1 text NOT NULL,
  player_2 text NOT NULL,
  player_3 text,
  player_4 text,
  winner_side int NOT NULL CHECK (winner_side IN (1, 2)),
  created_at timestamptz DEFAULT now(),
  CONSTRAINT fk_matches_player_1 FOREIGN KEY (player_1) REFERENCES public.players(name) ON UPDATE CASCADE,
  CONSTRAINT fk_matches_player_2 FOREIGN KEY (player_2) REFERENCES public.players(name) ON UPDATE CASCADE,
  CONSTRAINT fk_matches_player_3 FOREIGN KEY (player_3) REFERENCES public.players(name) ON UPDATE CASCADE,
  CONSTRAINT fk_matches_player_4 FOREIGN KEY (player_4) REFERENCES public.players(name) ON UPDATE CASCADE
);

-- =============================================================================
-- Row Level Security
-- =============================================================================
-- The data API is closed. No role reaches these tables except one that bypasses
-- RLS, so the app must connect with a secret key (sb_secret_*, which maps to
-- service_role); a publishable key gets nothing. That applies to the deployed
-- app and to the standalone scripts alike -- recalculate_ratings.py and
-- start_new_season.py read the same SUPABASE_KEY from a local secrets.toml.
--
-- Two independent layers, either of which alone would suffice:
--   1. RLS on with zero policies -- every row is filtered out for anon.
--   2. Grants revoked -- anon lacks table privileges in the first place, so a
--      carelessly permissive policy added later cannot by itself open a table.
-- Consequence of (2): granting public read someday takes a policy AND a
-- re-GRANT. A policy on its own will still return 401.

ALTER TABLE public.players  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.seasons  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.matches  ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.players, public.seasons, public.sessions, public.matches
  FROM anon, authenticated;
