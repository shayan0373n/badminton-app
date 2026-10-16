"""Pins the TrueSkillThroughTime calls ttt_logic relies on.

The library is vendored, so this guards the History / Player /
learning_curves usage against changes made to our copy.
"""

import math

import pytest
from scipy.optimize import brentq

from vendor.trueskillthroughtime import Gaussian, History, Player, fixed_point_approx

from constants import TTT_BETA, TTT_DEFAULT_MU, TTT_DEFAULT_SIGMA, TTT_GAMMA


def test_history_converges_and_reports_learning_curves():
    priors = {
        name: Player(Gaussian(mu=TTT_DEFAULT_MU, sigma=TTT_DEFAULT_SIGMA), beta=TTT_BETA, gamma=TTT_GAMMA)
        for name in ("a", "b", "c", "d")
    }
    history = History(
        composition=[[["a", "b"], ["c", "d"]], [["a", "c"], ["b", "d"]]],
        times=[1, 8],
        priors=priors,
        mu=TTT_DEFAULT_MU,
        sigma=TTT_DEFAULT_SIGMA,
        beta=TTT_BETA,
        gamma=TTT_GAMMA,
    )
    history.convergence(iterations=50)

    curves = history.learning_curves()
    assert history.size == 2
    day, skill = curves["a"][-1]
    assert day == 8
    # "a" won both games, so their estimate rises above the prior and tightens.
    assert skill.mu > TTT_DEFAULT_MU
    assert skill.sigma < TTT_DEFAULT_SIGMA


def _fixed_point_reference(r, mu, sigma):
    """Solves fixed_point_approx's equation with scipy's brentq, for comparison."""
    s2 = sigma**2

    def g(k):
        term = k - mu - r * s2 - 1
        numerator = mu + r * s2 - 1 - k + math.sqrt(term**2 + 2 * s2)
        return math.log(numerator / (2 * s2)) - k if numerator > 0 else -math.inf

    k = brentq(g, -20, 5)
    return mu + s2 * (r - math.exp(k)), math.sqrt(s2 / (1 + s2 * math.exp(k)))


@pytest.mark.parametrize(
    "r, mu, sigma",
    # Upstream v2.0.0 crashed on (0, 0, 1) and the three small-sigma cases,
    # and returned a wrong value for (1, 0, 1).
    [(0, 0.0, 1.0), (1, 0.0, 1.0), (2, -0.5, 2.0), (3, 0.0, 0.4), (5, 0.5, 0.3), (8, 0.0, 0.25)],
)
def test_fixed_point_approx_matches_a_reference_solver(r, mu, sigma):
    """Guards the local bisection fix to fixed_point_approx (score-based games)."""
    mu_new, sigma_new = fixed_point_approx(r, mu, sigma)
    want_mu, want_sigma = _fixed_point_reference(r, mu, sigma)

    assert mu_new == pytest.approx(want_mu, abs=1e-8)
    assert sigma_new == pytest.approx(want_sigma, abs=1e-8)
