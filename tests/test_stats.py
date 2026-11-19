"""The permutation tests behind the Analysis page."""
import numpy as np

import analyze


def test_ranks_share_ties():
    assert list(analyze.ranks([3, 1, 2, 2])) == [4, 1, 2.5, 2.5]


def pairs(look_k2p, random_k2p, focal="F"):
    return ([{"focal": focal, "kind": "lookalike", "k2p": d, "count": 1} for d in look_k2p]
            + [{"focal": focal, "kind": "random", "k2p": d} for d in random_k2p])


def test_closer_test_spots_close_lookalikes():
    np.random.seed(0)
    data = pairs([0.01, 0.02, 0.03, 0.04], [0.5, 0.6, 0.7, 0.8], "A") + pairs([0.02, 0.05, 0.03], [0.4, 0.9, 0.6], "B")
    result = analyze.closer_test(data, n=999)
    assert result["statistic"] > 0 and result["p"] < 0.01


def test_closer_test_finds_nothing_in_noise():
    np.random.seed(0)
    data = pairs([0.5, 0.1, 0.7, 0.3], [0.2, 0.6, 0.4, 0.8], "A")
    assert analyze.closer_test(data, n=999)["p"] > 0.2


def test_confusion_test_sign():
    np.random.seed(0)
    looks = [{"focal": "A" if i < 6 else "B", "k2p": 0.05 * i, "count": 100 - 10 * i} for i in range(12)]
    result = analyze.confusion_test(looks, n=999)
    assert result["rho"] < -0.9  # more confusion, closer DNA
