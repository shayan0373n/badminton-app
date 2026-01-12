-- =============================================================================
-- Badminton App Database Schema
-- =============================================================================
-- This schema defines the core tables for the Badminton App.
-- Run this script against your Supabase PostgreSQL database to initialize.
--
-- Default values for prior_mu and prior_sigma should match constants.py:
--   TTT_DEFAULT_MU = 25.0 (TTT_MU_AVERAGE)
--   TTT_DEFAULT_SIGMA = 6.0 (TTT_SIGMA_UNCERTAIN)
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
