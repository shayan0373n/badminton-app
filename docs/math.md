# Mathematical Foundations

This document describes the optimization formulation behind the matchmaking system. Each round, an integer program assigns players to courts and teams to minimize skill spread, power imbalance, and pairing staleness — subject to structural and social constraints.

---

## 1. Optimizer Inputs

### 1.1 Skill Estimates from TrueSkill Through Time

Player skill is modelled as a Gaussian $\mathcal{N}(\mu, \sigma^2)$ that evolves over time. The system uses [TrueSkill Through Time](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0210775) (Figueroa-Canabal 2019), a full-history Bayesian rating system that jointly infers skill trajectories from all recorded matches via expectation propagation. Unlike online systems (Elo, vanilla TrueSkill), TTT smooths estimates both forward and backward in time.

The optimizer consumes $\mu_i$ for each player $i$. It does not use $\sigma_i$ directly.

### 1.2 Two Rating Scales

The raw $\mu_i$ is projected onto two distinct scales on $[0, R]$ ($R = 5$), each serving a different objective term.

**Real skill** (team fairness) — direct linear rescaling that preserves the true performance gap:

$$r_i = \frac{\mu_i - \mu_{\min}}{\mu_{\max} - \mu_{\min}} \cdot R$$

**Tier rating** (court grouping) — Z-score normalization for gender-equitable grouping:

$$z_i = \frac{\mu_i - \bar{\mu}_{g_i}}{\sigma_{g_i}}, \qquad \tilde{\mu}_i = \bar{\mu}_M + z_i \cdot \sigma_M, \qquad \tau_i = \frac{\tilde{\mu}_i - \mu_{\min}}{\mu_{\max} - \mu_{\min}} \cdot R$$

where $\bar{\mu}_g, \sigma_g$ are the mean and std of $\mu$ within gender group $g$, and subscript $M$ denotes the male reference pool. A female at the 90th percentile of the female pool maps to the same tier as a male at the 90th percentile — producing organically mixed-gender courts without explicit quotas.

### 1.3 Session Performance Feedback

Within a session, players accumulate earned rating $e_i$ ($+1$ per win, $+0.5$ per rest). Before each round's optimization:

$$\mu_i^{\text{boost}} = \mu_i + 0.5 \cdot e_i$$

Players on a winning streak drift into harder matchups without modifying persistent ratings.

### 1.4 Court History

The optimizer tracks pairwise interaction counts across rounds:

$$h_{ij}^{\text{court}} = \text{times } i,j \text{ shared any court}, \qquad h_{ij}^{\text{partner}} = \text{times } i,j \text{ were teammates}$$

These feed the staleness penalty in the objective.

---

## 2. Match Optimization: Integer Linear Program

Given $n$ available players and $C$ courts with $k$ players each ($k=4$ for doubles, $k=2$ for singles), the optimizer solves the following ILP. The singles formulation is a reduced special case without partnership variables.

### 2.1 Decision Variables

| Variable | Domain | Semantics |
|----------|--------|-----------|
| $x_{p,c}$ | $\{0,1\}$ | Player $p$ assigned to court $c$ |
| $t_{ij,c}$ | $\{0,1\}$ | Players $i,j$ are **partners** (same team) on court $c$ |
| $s_{ij,c}$ | $\{0,1\}$ | Players $i,j$ share court $c$ (partners or opponents) |
| $\overline{\tau}_c, \underline{\tau}_c$ | $\mathbb{R}_{\geq 0}$ | Max / min tier rating on court $c$ |
| $\overline{w}_c, \underline{w}_c$ | $\mathbb{R}_{\geq 0}$ | Max / min team power on court $c$ |

### 2.2 Objective Function

$$\min \;\; \omega_s \underbrace{\sum_{c} \left(\overline{\tau}_c - \underline{\tau}_c\right)}_{\text{skill spread}} \;+\; \omega_p \underbrace{\sum_{c} \left(\overline{w}_c - \underline{w}_c\right)}_{\text{power imbalance}} \;+\; \omega_h \underbrace{\frac{1}{N_h} \sum_{c} \sum_{(i,j)} \left( s_{ij,c} \cdot h_{ij}^{\text{court}} + t_{ij,c} \cdot h_{ij}^{\text{partner}} \right)}_{\text{pairing staleness}}$$

- $\omega_s, \omega_p, \omega_h$ are user-adjustable weights (default: all 1.0)
- $N_h = 4$ is a normalization constant

**Skill spread** groups similar-tier players onto the same court. **Power imbalance** ensures the two teams on each court are evenly matched. **Pairing staleness** penalizes repeated pairings to prevent clique formation.

### 2.3 Structural Constraints

**Court capacity.** Each court gets exactly $k$ players:

$$\sum_{p} x_{p,c} = k \quad \forall\, c$$

**Player uniqueness.** Each player plays on at most one court:

$$\sum_{c} x_{p,c} \leq 1 \quad \forall\, p$$

**Full allocation.** All court slots are filled:

$$\sum_{p,c} x_{p,c} = k \cdot C$$

### 2.4 Partnership Constraints (Doubles)

Each player on a court has exactly one partner:

$$\sum_{j \neq p} t_{pj,c} = x_{p,c} \quad \forall\, p, c$$

Same-court indicator linking ($s_{ij,c} = 1 \iff$ both $i$ and $j$ on court $c$):

$$s_{ij,c} \leq x_{i,c}, \quad s_{ij,c} \leq x_{j,c}, \quad s_{ij,c} \geq x_{i,c} + x_{j,c} - 1 \quad \forall\, (i,j), c$$

### 2.5 Required Partnerships

Players may declare fixed partnerships. If player $p$ has required partner set $R_p$:

$$\sum_{q \in R_p} t_{pq,c} \geq x_{p,c} \quad \forall\, p \text{ with } R_p \neq \emptyset, \; \forall\, c$$

### 2.6 Skill and Power Balance (Big-M)

Min/max tier ratings on each court:

$$\overline{\tau}_c \geq \tau_p - M(1 - x_{p,c}), \qquad \underline{\tau}_c \leq \tau_p + M(1 - x_{p,c}) \quad \forall\, p, c$$

Team power (average real skill of a partnership pair):

$$w_{ij} = \frac{r_i + r_j}{2}$$

$$\overline{w}_c \geq w_{ij} - M(1 - t_{ij,c}), \qquad \underline{w}_c \leq w_{ij} + M(1 - t_{ij,c}) \quad \forall\, (i,j), c$$

$M = 1000$. When the assignment variable is 1, the bound is tight; when 0, the constraint is vacuous.

### 2.7 Problem Size

Binary variables: $O(n \cdot C + n^2 \cdot C)$, dominated by pairwise terms. For typical club sizes ($n \leq 30$, $C \leq 6$), solves within a 10-second time limit.

---

## 3. CP-SAT Backend (OR-Tools)

The OR-Tools backend solves the same problem using constraint programming, with three implementation differences:

1. **Conditional constraints replace Big-M.** CP-SAT natively supports $x_{p,c} = 1 \implies \overline{\tau}_c \geq \tau_p$, eliminating numerical sensitivity to $M$.

2. **Integer arithmetic.** Ratings are scaled to integers (factor of 100) to use CP-SAT's native integer domain, avoiding floating-point tolerance issues.

3. **Native boolean logic.** Variable linking uses implications ($s_{ij,c} \implies x_{i,c}$) translated directly into the SAT representation, rather than linear inequalities with auxiliary variables.

---

## 4. Rest Rotation

When $n > k \cdot C$, a FIFO queue determines who rests:

1. Players at the front rest first
2. After resting, they rotate to the back (shuffled to avoid positional bias)
3. Resting players receive $+0.5$ earned rating to compensate

This bounds rest imbalance: each player rests at most $\lceil n / (k \cdot C) \rceil - 1$ more times than any other.

---

## 5. System Diagram

```
              Match History (Supabase)
                        │
                        ▼
             ┌─────────────────────┐
             │  TrueSkill Through  │
             │       Time          │
             │  (Bayesian EP,      │
             │   50 iterations)    │
             └────────┬────────────┘
                      │
                μ_i per player
                      │
        ┌─────────────┴──────────────┐
        ▼                            ▼
 Z-score normalize              Direct scale
 (gender-relative)              (absolute)
        │                            │
        ▼                            ▼
      τ_i                          r_i
   ∈ [0, 5]                    ∈ [0, 5]
        │                            │
        └──────────┬─────────────────┘
                   │
        ┌──────────▼──────────┐
        │   ILP / CP-SAT      │
        │                     │
        │  min  ω_s·spread    │
        │     + ω_p·imbalance │
        │     + ω_h·staleness │
        │                     │
        │  s.t. capacity,     │
        │  partnership,       │
        │  required partners  │
        └──────────┬──────────┘
                   │
            Match assignments
                   │
                   ▼
           Session feedback
        (earned_rating → μ boost)
```

---

## References

1. Figueroa-Canabal, G. (2019). *TrueSkill Through Time.* PLOS ONE 14(1): e0210775.
2. Herbrich, R., Minka, T., & Graepel, T. (2007). *TrueSkill: A Bayesian Skill Rating System.* NeurIPS 19.
3. Gurobi Optimization, LLC. *Gurobi Optimizer Reference Manual.* https://www.gurobi.com
4. Perron, L., & Furnon, V. *OR-Tools CP-SAT Solver.* Google. https://developers.google.com/optimization
