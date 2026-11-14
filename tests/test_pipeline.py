"""Unit tests for the pure helpers in api/_radar/pipeline.py (no network calls)."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "api"))

from _radar import pipeline  # noqa: E402


# ---------------------------------------------------------------- canonical_url
class TestCanonicalUrl:
    def test_strips_tracking_params(self):
        url = "https://example.com/page?utm_source=twitter&utm_medium=social&id=42"
        assert pipeline.canonical_url(url) == "https://example.com/page?id=42"

    def test_strips_all_known_trackers(self):
        url = "https://example.com/a?fbclid=1&gclid=2&mc_cid=3&ref=site&igshid=4&si=5&q=hi"
        assert pipeline.canonical_url(url) == "https://example.com/a?q=hi"

    def test_tracking_match_is_case_insensitive(self):
        assert pipeline.canonical_url("https://example.com/a?UTM_Source=x&q=1") == "https://example.com/a?q=1"

    def test_keeps_non_tracking_params_with_similar_names(self):
        url = "https://example.com/a?referral=1&session=2"
        assert pipeline.canonical_url(url) == "https://example.com/a?referral=1&session=2"

    def test_sorts_remaining_query_params(self):
        assert pipeline.canonical_url("https://example.com/?b=2&a=1") == "https://example.com/?a=1&b=2"

    def test_strips_www_and_forces_https(self):
        assert pipeline.canonical_url("http://WWW.Example.com/A") == "https://example.com/A"

    def test_strips_m_prefix(self):
        assert pipeline.canonical_url("https://m.example.com/a") == "https://example.com/a"

    def test_strips_trailing_slashes(self):
        assert pipeline.canonical_url("https://www.example.com/a/b/") == "https://example.com/a/b"

    def test_root_paths(self):
        assert pipeline.canonical_url("https://www.example.com/") == "https://example.com/"
        assert pipeline.canonical_url("https://example.com") == "https://example.com/"

    def test_surrounding_whitespace_is_stripped(self):
        assert pipeline.canonical_url("  https://www.example.com/a  ") == "https://example.com/a"

    def test_drop_params_on_queryless_url(self):
        assert pipeline.canonical_url("https://example.com/a?utm_source=x") == "https://example.com/a"


# ------------------------------------------------------------- validate_passage
class TestValidatePassage:
    TEXT = "Acme announced on Tuesday that its platform suffered a four-hour outage."

    def test_verbatim_substring(self):
        assert pipeline.validate_passage("its platform suffered a four-hour outage", self.TEXT) is True

    def test_not_in_text(self):
        assert pipeline.validate_passage("Acme suffered a massive data breach", self.TEXT) is False

    def test_curly_vs_straight_quotes(self):
        text = 'The company replied: “we mishandled the data”, executives said.'
        passage = 'The company replied: "we mishandled the data", executives said.'
        assert pipeline.validate_passage(passage, text) is True
        assert pipeline.validate_passage(text, passage) is True

    def test_whitespace_and_case_differences(self):
        text = "The board reviewed the findings last week."
        passage = "  THE    board\nreviewed   the findings last week."
        assert pipeline.validate_passage(passage, text) is True

    def test_rejects_empty(self):
        assert pipeline.validate_passage("", self.TEXT) is False

    def test_rejects_too_short_even_if_present(self):
        text = "This is very short."
        assert pipeline.validate_passage("very short", text) is False  # 10 chars < 12


# ---------------------------------------------------------------- pick_evidence
class TestPickEvidence:
    def test_uses_verbatim_claim_passage(self):
        doc = {"text": "The regulator opened an investigation into Acme."}
        facts = {"claims": [{"claim": "regulator investigation",
                             "supporting_passage": "The regulator opened an investigation into Acme."}]}
        ev = pipeline.pick_evidence(doc, facts)
        assert ev["verified"] is True
        assert ev["origin"] == "ndi_claim"
        assert ev["passage"] == "The regulator opened an investigation into Acme."

    def test_falls_back_to_verbatim_citation(self):
        doc = {"text": "Employees complained about the layoffs in the memo."}
        facts = {
            "claims": [{"claim": "x", "supporting_passage": "NOT present in the article body."}],
            "_fields": [{"citations": [{"source_text": "Employees complained about the layoffs in the memo."}]}],
        }
        ev = pipeline.pick_evidence(doc, facts)
        assert ev["verified"] is True
        assert ev["origin"] == "ndi_citation"

    def test_unverified_returns_note(self):
        doc = {"text": "Unrelated content in the article."}
        facts = {"claims": [{"claim": "x",
                             "supporting_passage": "This passage does not appear verbatim anywhere."}]}
        ev = pipeline.pick_evidence(doc, facts)
        assert ev["verified"] is False
        assert ev["passage"] is None
        assert ev["origin"] is None
        assert ev["note"]

    def test_no_facts(self):
        ev = pipeline.pick_evidence({"text": "some text"}, None)
        assert ev["verified"] is False
        assert ev["passage"] is None


# ---------------------------------------------------------------- apply_policy
def make_decision(*, p_yes=None, action="watch", action_conf=0.9,
                  is_novel=None, report_type="news_report"):
    return {
        "is_subject": {"value": None, "p_yes": p_yes, "confidence": None},
        "category": {"value": "other", "confidence": None, "probabilities": {}},
        "report_type": {"value": report_type, "confidence": None, "probabilities": {}},
        "is_novel": {"value": is_novel, "p_yes": None, "confidence": None},
        "action": {"value": action, "confidence": action_conf, "probabilities": {}},
        "urgency": {"score": None, "confidence": None, "probabilities": {}, "legend": None},
    }


class TestApplyPolicy:
    def test_namesake_below_035_is_ignored(self):
        out = pipeline.apply_policy(make_decision(p_yes=0.2, action="review_now"))
        assert out["final_action"] == "ignore"
        assert "namesake_or_unrelated" in out["flags"]

    def test_uncertain_identity_bumps_ignore_to_watch(self):
        out = pipeline.apply_policy(make_decision(p_yes=0.5, action="ignore"))
        assert out["final_action"] == "watch"
        assert "identity_uncertain" in out["flags"]

    def test_uncertain_identity_keeps_review_now(self):
        out = pipeline.apply_policy(make_decision(p_yes=0.35, action="review_now"))
        assert out["final_action"] == "review_now"
        assert "identity_uncertain" in out["flags"]

    def test_uncertain_identity_is_at_least_watch(self):
        # An uncertain identity should never be filed below watch.
        out = pipeline.apply_policy(make_decision(p_yes=0.4, action="digest"))
        assert out["final_action"] == "watch"
        assert "identity_uncertain" in out["flags"]

    def test_confident_identity_unchanged(self):
        out = pipeline.apply_policy(make_decision(p_yes=0.9, action="review_now", is_novel=True))
        assert out["final_action"] == "review_now"
        assert out["flags"] == []

    def test_no_probability_yields_no_identity_flags(self):
        out = pipeline.apply_policy(make_decision(p_yes=None, action="ignore"))
        assert out["final_action"] == "ignore"
        assert out["flags"] == []

    def test_repeat_coverage_downgrades_review_now(self):
        out = pipeline.apply_policy(make_decision(p_yes=0.9, action="review_now", is_novel=False))
        assert out["final_action"] == "watch"
        assert "repeat_coverage_downgraded" in out["flags"]

    def test_no_downgrade_when_novel(self):
        out = pipeline.apply_policy(make_decision(p_yes=0.9, action="review_now", is_novel=True))
        assert out["final_action"] == "review_now"
        assert "repeat_coverage_downgraded" not in out["flags"]

    def test_no_downgrade_when_action_is_not_review_now(self):
        out = pipeline.apply_policy(make_decision(p_yes=0.9, action="watch", is_novel=False))
        assert out["final_action"] == "watch"
        assert "repeat_coverage_downgraded" not in out["flags"]

    def test_allegation_flag(self):
        out = pipeline.apply_policy(make_decision(p_yes=0.9, report_type="allegation"))
        assert out["final_action"] == "watch"
        assert "allegation_not_fact" in out["flags"]

    def test_allegation_combined_with_repeat_downgrade(self):
        out = pipeline.apply_policy(
            make_decision(p_yes=0.9, action="review_now", is_novel=False, report_type="allegation"))
        assert out["final_action"] == "watch"
        assert "repeat_coverage_downgraded" in out["flags"]
        assert "allegation_not_fact" in out["flags"]

    def test_low_confidence_action_flag(self):
        out = pipeline.apply_policy(make_decision(p_yes=0.9, action="watch", action_conf=0.4))
        assert "low_confidence_action" in out["flags"]

    def test_missing_confidence_is_not_low(self):
        out = pipeline.apply_policy(make_decision(p_yes=0.9, action="watch", action_conf=None))
        assert "low_confidence_action" not in out["flags"]


# --------------------------------------------------------------------- _as_bool
class TestAsBool:
    def test_native_bools(self):
        assert pipeline._as_bool(True) is True
        assert pipeline._as_bool(False) is False

    def test_string_form(self):
        assert pipeline._as_bool("true") is True
        assert pipeline._as_bool("FALSE") is False
        assert pipeline._as_bool("  Yes ") is True
        assert pipeline._as_bool("no") is False

    def test_unrecognized_values(self):
        assert pipeline._as_bool("maybe") is None
        assert pipeline._as_bool(1) is None
        assert pipeline._as_bool(0) is None
        assert pipeline._as_bool(None) is None
