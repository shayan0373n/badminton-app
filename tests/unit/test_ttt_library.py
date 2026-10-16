"""Pins the TrueSkillThroughTime calls ttt_logic relies on.

The library is vendored, so this guards the History / Player /
learning_curves usage against changes made to our copy.
"""

from vendor.trueskillthroughtime import Gaussian, History, Player

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
