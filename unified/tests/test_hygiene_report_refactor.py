"""Tests for get_test_data_hygiene_report extracted helpers."""

from __future__ import annotations
import pytest


class TestComputeHiddenRatios:
    def test_zero_active_returns_zero_ratio(self):
        from src.memory_reads import _compute_hidden_ratios

        ratio, by_domain = _compute_hidden_ratios(
            hidden_counts={},
            visible_status_counts={},
            visible_domain_status_counts={},
        )
        assert ratio == 0.0
        assert by_domain == {"build": 0.0, "corporate": 0.0, "personal": 0.0}

    def test_computes_ratio_correctly(self):
        from src.memory_reads import _compute_hidden_ratios

        ratio, by_domain = _compute_hidden_ratios(
            hidden_counts={"hidden_test_data_active_total": 1},
            visible_status_counts={"active": 3},
            visible_domain_status_counts={},
        )
        # 1 hidden / (3 visible + 1 hidden) = 0.25
        assert ratio == 0.25

    def test_build_domain_ratio(self):
        from src.memory_reads import _compute_hidden_ratios

        ratio, by_domain = _compute_hidden_ratios(
            hidden_counts={
                "hidden_test_data_active_total": 0,
                "hidden_test_data_build_total": 2,
            },
            visible_status_counts={"active": 0},
            visible_domain_status_counts={"build": {"active": 2}},
        )
        # 2 hidden build / (2 visible build + 2 hidden build) = 0.5
        assert by_domain["build"] == 0.5


class TestBuildHygieneRecommendations:
    def test_no_test_data_returns_no_action_needed(self):
        from src.memory_reads import _build_hygiene_recommendations

        actions = _build_hygiene_recommendations(
            hidden_counts={"hidden_test_data_total": 0},
            hidden_active_ratio=0.0,
            null_match_key_count=0,
            top_owners={},
        )
        assert len(actions) == 1
        assert actions[0].code == "no_action_needed"

    def test_build_data_recommends_cleanup(self):
        from src.memory_reads import _build_hygiene_recommendations

        actions = _build_hygiene_recommendations(
            hidden_counts={
                "hidden_test_data_total": 5,
                "hidden_test_data_build_total": 5,
            },
            hidden_active_ratio=0.1,
            null_match_key_count=0,
            top_owners={},
        )
        codes = [a.code for a in actions]
        assert "cleanup_build_test_data" in codes

    def test_high_ratio_recommends_elevated_alert(self):
        from src.memory_reads import _build_hygiene_recommendations

        actions = _build_hygiene_recommendations(
            hidden_counts={
                "hidden_test_data_total": 10,
                "hidden_test_data_build_total": 0,
            },
            hidden_active_ratio=0.30,
            null_match_key_count=0,
            top_owners={},
        )
        codes = [a.code for a in actions]
        assert "hidden_ratio_elevated" in codes

    def test_null_match_keys_recommends_normalize(self):
        from src.memory_reads import _build_hygiene_recommendations

        actions = _build_hygiene_recommendations(
            hidden_counts={"hidden_test_data_total": 1},
            hidden_active_ratio=0.0,
            null_match_key_count=3,
            top_owners={},
        )
        codes = [a.code for a in actions]
        assert "normalize_missing_match_keys" in codes
