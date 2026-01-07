# Mathematical Definition of Partner Constraints

## 1. Problem Definition

We are optimizing a match schedule for a set of players $P$.
Let $x_i \in \{0, 1\}$ be a decision variable where $x_i = 1$ implies player $i$ is playing in this round.
Let $t_{ij} \in \{0, 1\}$ be a decision variable where $t_{ij} = 1$ implies player $i$ and player $j$ are partners.

We define a graph of **Required Partners** where $j \in R_i$ means player $i$ is required to partner with player $j$.
Note that this graph is undirected in practice (if $i$ needs $j$, $j$ needs $i$), but we define the constraints per player.
Strictly, $R_i$ is the set of valid specialized partners for $i$.

### The Flaw in Strict Constraints

The standard constraint for partnership enforcement is:
$$ \sum_{j \in R_i} t_{ij} \ge x_i \quad \text{(Constraint A)} $$

This states: "If player $i$ plays, they **must** play with a partner from their required list."

**The Hub Failure Mode:**
Consider a set $\{P_1, P_2, P_3\}$ where $P_1$ is the "Hub":
*   $R_{P1} = \{P_2, P_3\}$
*   $R_{P2} = \{P_1\}$
*   $R_{P3} = \{P_1\}$

If the optimizer selects the partnership $(P_1, P_2)$:
1.  **For $P_1$**: $\sum t_{1j} = t_{1,2} = 1$. Since $1 \ge 1$, constraint satisfied.
2.  **For $P_2$**: $\sum t_{2j} = t_{2,1} = 1$. Since $1 \ge 1$, constraint satisfied.
3.  **For $P_3$**: $\sum t_{3j} = t_{3,1} = 0$. Since $P_1$ is already matched with $P_2$, $t_{3,1}$ must be 0.
    The constraint becomes $0 \ge x_{P3}$, forcing $x_{P3} = 0$.
    Thus, $P_3$ is forced to sit out simply because their specific partner picked a teammate.

---

## 2. Solution Part 1: The "Validly Occupied" Constraint

To fix the Hub Failure Mode, we relax the condition to allow a player to play with *anyone* (including non-required partners) if their required partners are **validly occupied** with another mutual teammate.

$$ \sum_{j \in R_i} \left( t_{ij} + \sum_{k \in R_j \setminus \{i\}} t_{jk} \right) \ge x_i \quad \text{(Constraint B)} $$

This successfully handles cases where all players are *available* to play.

---

## 3. Solution Part 2: Addressing Forced Rests (The Infeasibility Trap)

**Scenario:** $P_1$ (Hub) is forced to rest by the session manager (e.g., rotation logic).
*   $x_1$ is forced to 0.
*   For $P_2$ (needs $P_1$): Constraint B becomes $t_{2,1} + \sum (\dots) \ge x_2$.
*   Since $P_1$ is resting, $t_{2,1}=0$ and $P_1$ cannot partner with anyone else (so $\sum=0$).
*   Result: $0 \ge x_2$. $P_2$ is forced to rest.
*   Similarly, $P_3$ is forced to rest.
If we needed 4 players for a court and only had 5 total, forcing 3 to sit out (P1+P2+P3) leaves only 2 players. **Infeasible.**

### The Corrected "Availability-Aware" Constraint

We must filter the requirements based on who is actually present in the **Available Pool** ($A_{pool}$).

Let $R_i^{active} = R_i \cap A_{pool}$ be the set of partners for $i$ who are physically allowed to play this round.

**Rule:**
1.  If $R_i^{active} = \emptyset$: The player has no teammates present/allowed. They are **released** from all constraints and can play with anyone.
2.  If $R_i^{active} \neq \emptyset$: The constraint applies, but *only* considering active partners.

$$ \sum_{j \in R_i^{active}} \left( t_{ij} + \sum_{k \in R_j \setminus \{i\}} t_{jk} \right) \ge x_i \quad \text{(Final Constraint)} $$

---

## 4. Verification on Scenarios

### Scenario A: The Hub (All Available)
*Setup: $P_1$ (Hub) active, $P_2, P_3$ active. $R_2=\{1\}, R_3=\{1\}$. $P_1$ plays with $P_2$.*
*   **$P_3$ Status**:
    *   $R_3^{active} = \{P_1\}$.
    *   Check: $t_{3,1} + t_{1,2} \ge x_3$.
    *   $0 + 1 \ge x_3 \implies 1 \ge x_3$.
    *   **Result**: $P_3$ is **Excused** (Validly Occupied rule). Can play with anyone.

### Scenario B: Hub Forced Rest
*Setup: $P_1$ forced to rest ($P_1 \notin A_{pool}$). $P_2, P_3$ active. $R_2=\{1\}, R_3=\{1\}$.*
*   **$P_2$ Status**:
    *   $R_2^{active} = R_2 \cap \{P_2, P_3, \dots\} = \{1\} \cap \{2, 3, \dots\} = \emptyset$.
    *   **Result**: $R_2^{active}$ is empty. Constraint dropped. $P_2$ works as a free agent.
*   **$P_3$ Status**:
    *   Same logic. $P_3$ works as a free agent.
    *   **Result**: $P_2$ and $P_3$ can play together or with strangers. **Feasible.**

### Scenario C: Partial Team Rest ($P_2$ Rests)
*Setup: $P_2$ forced rest. $P_1, P_3$ active. $R_1=\{2,3\}, R_3=\{1\}$.*
*   **$P_3$ Status**:
    *   $R_3^{active} = \{1\}$.
    *   Constraint: $t_{3,1} + (\text{Is } P_1 \text{ busy with } P_2?) \ge x_3$.
    *   Since $P_2$ is resting, $P_1$ cannot be busy with $P_2$. Term is 0.
    *   Constraint simplifies to: $t_{3,1} \ge x_3$.
    *   **Result**: $P_3$ **MUST** play with $P_1$. (Correct).
*   **$P_1$ Status**:
    *   $R_1^{active} = \{3\}$.
    *   Constraint simplifies to: $t_{1,3} \ge x_1$.
    *   **Result**: $P_1$ **MUST** play with $P_3$. (Correct).

## 4. Conclusion

The **Availability-Aware Validly-Occupied Constraint** correctly handles:
1.  **Hub selection**: Valid teams play, left-over members are excused.
2.  **Forced Rests**: If the team captain (Hub) is forced out, the team is freed.
3.  **Strictness**: If the team is here, you must play with them (unless they are busy with each other).
