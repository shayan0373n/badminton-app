/**
 * Admin: the rating table and the recalculate button.
 *
 * Reached only by typing /admin; nothing in the app links here. It is for the
 * organizer after a night, not for the door, so it stays off the main flow.
 */

import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { RegistryPlayer } from "../types";

type Column = keyof Pick<RegistryPlayer, "name" | "prior_mu" | "mu" | "sigma" | "rating">;

const COLUMNS: { key: Column; label: string }[] = [
  { key: "name", label: "Player" },
  { key: "prior_mu", label: "Prior μ" },
  { key: "mu", label: "μ" },
  { key: "sigma", label: "σ" },
  { key: "rating", label: "Conservative" },
];

export function AdminScreen() {
  const [registry, setRegistry] = useState<RegistryPlayer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [recalculating, setRecalculating] = useState(false);
  const [sortBy, setSortBy] = useState<Column>("mu");
  const [descending, setDescending] = useState(true);

  useEffect(() => {
    api
      .listPlayers()
      .then((p) => setRegistry(p.players))
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load."))
      .finally(() => setLoading(false));
  }, []);

  async function recalculate() {
    setError(null);
    setNotice(null);
    setRecalculating(true);
    try {
      const { players, matches } = await api.recalculateRatings();
      setNotice(`Ratings recalculated for ${players} players from ${matches} matches this season.`);
      setRegistry((await api.listPlayers()).players);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not recalculate ratings.");
    } finally {
      setRecalculating(false);
    }
  }

  function sortOn(column: Column) {
    if (column === sortBy) {
      setDescending((d) => !d);
    } else {
      setSortBy(column);
      // Names read top-down; numbers want the strongest first.
      setDescending(column !== "name");
    }
  }

  // Unrated players sink to the end whichever way the numbers are sorted.
  const ranked = useMemo(() => {
    const sign = descending ? -1 : 1;
    return [...registry].sort((a, b) => {
      const x = a[sortBy];
      const y = b[sortBy];
      if (x === null) return y === null ? 0 : 1;
      if (y === null) return -1;
      if (typeof x === "string" && typeof y === "string") {
        return sign * x.localeCompare(y, undefined, { sensitivity: "base" });
      }
      return sign * ((x as number) - (y as number));
    });
  }, [registry, sortBy, descending]);

  return (
    <div className="app">
      <header className="topbar">
        <a className="btn btn-icon" href="/" aria-label="Back to setup">
          ←
        </a>
        <h1>Ratings</h1>
        <span className="sub">{registry.length} members</span>
      </header>

      <div className="content">
        {error && <div className="banner banner-error">{error}</div>}
        {notice && <div className="banner banner-info">{notice}</div>}
        {loading && <p className="hint">Loading…</p>}

        <section className="section">
          <div className="section-head">
            <h2>Recalculate</h2>
          </div>
          <p className="hint">
            Rebuilds this season's ratings from every recorded match. Run it after
            uploading a night's results.
          </p>
          <button className="btn btn-primary" disabled={recalculating} onClick={recalculate}>
            {recalculating ? "Recalculating…" : "Recalculate ratings"}
          </button>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>Rating table</h2>
          </div>
          <table className="standings sortable">
            <thead>
              <tr>
                <th className="num">#</th>
                {COLUMNS.map((c) => (
                  <th
                    key={c.key}
                    className={c.key === "name" ? undefined : "num"}
                    aria-sort={
                      c.key === sortBy ? (descending ? "descending" : "ascending") : "none"
                    }
                  >
                    <button type="button" onClick={() => sortOn(c.key)}>
                      {c.label}
                      {c.key === sortBy && <span className="sort-mark">{descending ? "▼" : "▲"}</span>}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ranked.map((p, i) => (
                <tr key={p.name}>
                  <td className="num">{i + 1}</td>
                  <td>{p.name}</td>
                  <td className="num">{p.prior_mu.toFixed(2)}</td>
                  <td className="num">{fmt(p.mu)}</td>
                  <td className="num">{fmt(p.sigma)}</td>
                  <td className="num">{fmt(p.rating)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}

function fmt(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}
