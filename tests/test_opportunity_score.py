"""Regression tests for the #28 opportunity score (acceptance-probability ranking).

All fixtures are static dicts shaped like GitHub search/issues API items; no
network access is needed. See issue yunaremaia/oss-contribution-finder#28.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))

import pytest

from oss_contribution_finder import opportunity_score


NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)


def make_issue(stars, labels, created_days_ago=5, assignees=None, repo_name=None, **extra):
    """Build an issue item shaped like a search API + enrich result."""
    item = {
        "title": "Fix bug",
        "html_url": f"https://github.com/{repo_name}/repo/issues/1",
        "created_at": (NOW - timedelta(days=created_days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "labels": [{"name": label} for label in labels],
        "assignees": assignees or [],
        "repo": {
            "full_name": repo_name or f"a/{stars}",
            "stargazers_count": stars,
        },
    }
    item.update(extra)
    return item


# The issue's headline acceptance criterion: a 200-star repo with a
# good-first-issue label must rank ABOVE a 50k-star repo with the same label,
# same assignee state and age.
def test_low_star_good_first_issue_outranks_high_star():
    low_star = make_issue(200, ["good first issue"], repo_name="small/repo")
    high_star = make_issue(50_000, ["good first issue"], repo_name="big/repo")
    assert opportunity_score(low_star, now=NOW) > opportunity_score(high_star, now=NOW)


def test_assigned_issue_deprioritized():
    unassigned = make_issue(200, ["good first issue"], repo_name="a/repo")
    assigned = make_issue(200, ["good first issue"], assignees=[{"login": "dev"}],
                          repo_name="a/repo")
    assert opportunity_score(assigned, now=NOW) < opportunity_score(unassigned, now=NOW)


def test_recency_window_pinned_to_issue_formula():
    """recency = max(0, 1 - age_days/180); at 180 days it contributes 0."""
    issue_180d = make_issue(200, [], created_days_ago=180, repo_name="a/repo")
    fresh = make_issue(200, [], created_days_ago=0, repo_name="a/repo")
    score_180d = opportunity_score(issue_180d, now=NOW)
    score_fresh = opportunity_score(fresh, now=NOW)
    assert score_180d == pytest.approx(0.35 * 1.0 + 0.20 * 1.0 + 0.10 * 0.0)
    assert score_fresh == pytest.approx(score_180d + 0.10)
    assert score_fresh > score_180d


def test_competition_tier_boundaries():
    # Issue's tiers: <=500 -> 1.0, <=5000 -> 0.5, otherwise 0.1.
    star_500 = make_issue(500, [], repo_name="a/repo")
    star_501 = make_issue(501, [], repo_name="a/repo")
    star_5000 = make_issue(5000, [], repo_name="a/repo")
    star_5001 = make_issue(5001, [], repo_name="a/repo")
    assert opportunity_score(star_500, now=NOW) > opportunity_score(star_501, now=NOW)
    assert opportunity_score(star_5000, now=NOW) > opportunity_score(star_5001, now=NOW)


def test_label_tiers():
    gfi = make_issue(100, ["good-first-issue"], repo_name="a/repo")
    hw = make_issue(100, ["help wanted"], repo_name="a/repo")
    bug = make_issue(100, ["bug"], repo_name="a/repo")
    none = make_issue(100, [], repo_name="a/repo")
    assert opportunity_score(gfi, now=NOW) > opportunity_score(hw, now=NOW)
    assert opportunity_score(hw, now=NOW) > opportunity_score(bug, now=NOW)
    assert opportunity_score(bug, now=NOW) > opportunity_score(none, now=NOW)


def test_two_label_items_average_to_top_label():
    """A repo can attach both good-first-issue and bug; the item keeps the top tier."""
    both = make_issue(100, ["bug", "good first issue"], repo_name="a/repo")
    gfi_only = make_issue(100, ["good first issue"], repo_name="a/repo")
    rando = make_issue(100, ["enhancement"], repo_name="a/repo")
    assert opportunity_score(both, now=NOW) == pytest.approx(
        opportunity_score(gfi_only, now=NOW))
    assert opportunity_score(rando, now=NOW) < opportunity_score(both, now=NOW)


def test_missing_fields_do_not_crash_and_score_conservatively():
    # No repo dict (unenriched), no labels, no assignees, no created_at.
    bare = {"title": "Unknown"}
    score = opportunity_score(bare, now=NOW)  # must not raise
    assert score == pytest.approx(0.35 * 1.0 + 0.20 * 1.0 + 0.10 * 0.0)


def test_score_stays_within_unit_range():
    # Fully favourable: <=500 stars, good-first-issue, unassigned, brand new.
    best = make_issue(0, ["good first issue"], created_days_ago=0, repo_name="a/repo")
    worst = make_issue(10**7, ["enhancement"], created_days_ago=365,
                       assignees=[{"login": "x"}], repo_name="a/repo")
    assert 0.0 < opportunity_score(best, now=NOW) <= 1.0
    assert 0.0 <= opportunity_score(worst, now=NOW) < 0.1


def test_labels_as_plain_strings_also_scored():
    # Formatters/tests elsewhere pass labels as plain strings; keep symmetrical.
    item = make_issue(100, ["good first issue"], repo_name="a/repo")
    item["labels"] = ["good first issue"]
    assert opportunity_score(item, now=NOW) > opportunity_score(
        make_issue(100, [], repo_name="a/repo"), now=NOW)


def _contributor_404s(count):
    return [{"error": 404}] * count


def test_cli_sort_score_ranks_low_star_repo_first(capsys):
    items = [
        {"title": "High-star repo issue", "repo": {"full_name": "big/repo",
                                                   "stargazers_count": 50_000},
         "labels": [{"name": "good first issue"}], "assignees": [],
         "created_at": (NOW - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "repository_url": "https://api.github.com/repos/big/repo"},
        {"title": "Low-star repo issue", "repo": {"full_name": "small/repo",
                                                  "stargazers_count": 200},
         "labels": [{"name": "good first issue"}], "assignees": [],
         "created_at": (NOW - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "repository_url": "https://api.github.com/repos/small/repo"},
    ]
    with patch("sys.argv", ["finder", "--no-enrich", "--sort", "score", "--format", "json"]), \
         patch("oss_contribution_finder.get_token", return_value=None), \
         patch("oss_contribution_finder.search_issues", return_value={"items": items}), \
         patch("oss_contribution_finder.api_request", side_effect=_contributor_404s(6)):
        from oss_contribution_finder import main
        main()
    out = json.loads(capsys.readouterr().out)
    assert [item["title"] for item in out] == ["Low-star repo issue", "High-star repo issue"]
    assert out[0]["opportunity_score"] > out[1]["opportunity_score"]


def test_cli_sort_score_still_runs_contributor_checks(capsys):
    items = [{"title": "One", "repo": {"full_name": "a/repo", "stargazers_count": 100},
              "labels": [{"name": "good first issue"}], "assignees": [],
              "created_at": (NOW - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "repository_url": "https://api.github.com/repos/a/repo"}]
    with patch("sys.argv", ["finder", "--no-enrich", "--sort", "score", "--format", "json"]), \
         patch("oss_contribution_finder.get_token", return_value=None), \
         patch("oss_contribution_finder.search_issues", return_value={"items": items}), \
         patch("oss_contribution_finder.api_request", side_effect=_contributor_404s(3)) as api:
        from oss_contribution_finder import main
        main()
    assert json.loads(capsys.readouterr().out)[0]["contributor_friendly"] is False
    assert api.call_count == 3


def test_build_parser_accepts_score_sort():
    args = __import__("oss_contribution_finder").build_parser().parse_args(["--sort", "score"])
    assert args.sort == "score"
