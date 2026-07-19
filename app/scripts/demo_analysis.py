"""Hand-crafted post-call analysis aligned with demo_transcripts.py scenarios."""

from __future__ import annotations

from typing import Any

from app.analysis.post_call_analysis import (
    PostCallAnalysisResult,
    apply_computed_metrics,
    enrich_call_timeline,
    finalize_dashboard_metrics,
)


def _profiles(first: str) -> dict[str, dict[str, Any]]:
    return {
        "7d593e0a-aa11-4151-b42f-4258468098c3": {
            "executive_summary": (
                "Rajesh called about a Goregaon three BHK with sea view, sharing a two crore budget, "
                "six-month move-in, and commute needs. The rep qualified parking, floor band, maintenance, "
                "and payment plan, then secured a Saturday site visit with token discussion on site."
            ),
            "primary_intent": "property_inquiry",
            "intent_summary": "Family upgrade in Goregaon West with sea glimpse, comparing Lodha, ready to visit.",
            "interest_score": 88,
            "conversion_pct": 76,
            "conversion_rationale": "Prospect shared email, requested full document pack, and committed to Saturday visit with token intent.",
            "buying_signals": [
                {"signal": "site visit scheduled", "evidence_quote": "Saturday around ten works", "confidence": 0.92},
                {"signal": "token readiness", "evidence_quote": "we can discuss token amount on the spot", "confidence": 0.9},
                {"signal": "budget alignment", "evidence_quote": "Around two crore, maybe stretch to two point two", "confidence": 0.86},
                {"signal": "document request", "evidence_quote": "send the brochure, payment plan, and maintenance sheet", "confidence": 0.84},
            ],
            "objections": [
                {"objection": "maintenance charges", "evidence_quote": "worried about the maintenance charges", "severity": "medium"},
                {"objection": "competitor comparison", "evidence_quote": "comparing Lodha's project in the same belt", "severity": "low"},
                {"objection": "view clarity", "evidence_quote": "western view actually sea view or just city skyline", "severity": "medium"},
            ],
            "open_questions": ["HDFC subvention rate for selected tower"],
            "rep_assessment": f"{first} ran a balanced discovery call — strong qualification, honest view guidance, and a concrete close.",
            "strengths": ["Asked budget and timeline early", "Handled maintenance with specifics", "Clarified sea glimpse by floor"],
            "coaching": [{"area": "finance", "recommendation": "Confirm subvention grid before the Saturday visit.", "example_moment_ms": 144000}],
            "topics": [{"name": "pricing", "weight": 0.28}, {"name": "location", "weight": 0.22}, {"name": "amenities", "weight": 0.18}, {"name": "payment_plan", "weight": 0.16}],
            "pivotal": [{"start_ms": 166500, "label": "email requested", "quote": "send the brochure, payment plan", "why_it_matters": "Shifted from ad response to active evaluation."}],
            "next_steps": [
                {"owner": "rep", "action": "send brochure, payment plan, maintenance sheet", "due_hint": "today"},
                {"owner": "prospect", "action": "site visit Saturday 10 AM", "due_hint": "this week"},
            ],
            "sentiment": {"opening": "curious", "middle": "engaged", "closing": "positive", "opening_score": 58, "middle_score": 72, "closing_score": 82},
        },
        "c41e8f20-6b2d-4a91-9f3e-2d8a7c15e401": {
            "executive_summary": (
                "An investor prospect explored Thane West two BHK for rental yield, validating carpet, RERA timeline, "
                "payment plan, and HDFC subvention. The rep held unit fourteen zero three and booked a Thursday visit "
                "with token intent if numbers match."
            ),
            "primary_intent": "investment_inquiry",
            "intent_summary": "Yield-focused buyer with 1.4 Cr cap and thirty-day closing window.",
            "interest_score": 84,
            "conversion_pct": 74,
            "conversion_rationale": "Prospect requested unit hold and committed to token on visit if yield deck checks out.",
            "buying_signals": [
                {"signal": "token intent", "evidence_quote": "token can happen on visit", "confidence": 0.9},
                {"signal": "unit hold", "evidence_quote": "hold fourteen zero three", "confidence": 0.88},
                {"signal": "yield threshold stated", "evidence_quote": "net yield crosses three point five percent", "confidence": 0.82},
            ],
            "objections": [
                {"objection": "possession proof", "evidence_quote": "delay history on this tower", "severity": "medium"},
            ],
            "open_questions": ["ICICI subvention grid vs HDFC pre-approval"],
            "rep_assessment": f"{first} qualified investor criteria well and proposed a concrete hold plus visit.",
            "strengths": ["Clarified rental comps", "Shared milestone proof", "Closed with unit hold"],
            "coaching": [],
            "topics": [{"name": "pricing", "weight": 0.3}, {"name": "possession", "weight": 0.24}, {"name": "finance", "weight": 0.2}],
            "pivotal": [{"start_ms": 123000, "label": "unit hold", "quote": "hold fourteen zero three", "why_it_matters": "Inventory risk reduced with named stack."}],
            "next_steps": [{"owner": "rep", "action": "send yield deck and maintenance breakup", "due_hint": "today"}],
            "sentiment": {"opening": "businesslike", "middle": "focused", "closing": "positive", "opening_score": 62, "middle_score": 74, "closing_score": 80},
        },
        "d52f9a31-7c3e-5b02-a04f-3e9b8d26f512": {
            "executive_summary": (
                "Anil and Priya Shah enquired on Dadar sea-facing three BHK within three crore all-in. "
                "Architect review is required before visit; rep offered CAD plans, stamp duty note, and tentative Sunday slot."
            ),
            "primary_intent": "layout_evaluation",
            "intent_summary": "High-intent family buyer pending architect sign-off on deck layout.",
            "interest_score": 76,
            "conversion_pct": 70,
            "conversion_rationale": "Budget fits inventory; conditional Sunday visit if CAD plans pass architect review.",
            "buying_signals": [
                {"signal": "conditional visit", "evidence_quote": "Sunday eleven is likely", "confidence": 0.82},
                {"signal": "document request", "evidence_quote": "Send CAD plans, stamp duty note", "confidence": 0.8},
            ],
            "objections": [
                {"objection": "carpet size", "evidence_quote": "At least one thousand one hundred square feet carpet", "severity": "medium"},
                {"objection": "competitor comparison", "evidence_quote": "also looking at a Wadhwa project nearby", "severity": "low"},
            ],
            "open_questions": ["stamp duty benefits this quarter", "festive floor-rise waiver eligibility"],
            "rep_assessment": f"{first} respected architect gate and kept momentum with finance and CAD follow-up.",
            "strengths": ["Identified decision makers", "Offered CAD plans same day"],
            "coaching": [{"area": "finance", "recommendation": "Send stamp duty note bundled with CAD pack.", "example_moment_ms": 106500}],
            "topics": [{"name": "layout", "weight": 0.3}, {"name": "pricing", "weight": 0.24}, {"name": "amenities", "weight": 0.18}],
            "pivotal": [],
            "next_steps": [{"owner": "rep", "action": "send CAD plans and stamp duty note", "due_hint": "tonight"}],
            "sentiment": {"opening": "interested", "middle": "evaluating", "closing": "cautious", "opening_score": 60, "middle_score": 68, "closing_score": 72},
        },
        "e63a0b42-8d4f-6c13-b15a-4f0c9e37a623": {
            "executive_summary": (
                "Prospect compared Raymond Thane West with Lodha Palava on possession, subvention, maintenance, and commute. "
                "Engagement stayed high but visit was deferred until legal delay clause and finance grid are documented."
            ),
            "primary_intent": "competitive_evaluation",
            "intent_summary": "Active Lodha comparison; needs written proof on loan, society cost, and penalty clause.",
            "interest_score": 60,
            "conversion_pct": 50,
            "conversion_rationale": "Refused site visit until documentation arrives; Tuesday visit only if gap vs Palava is small.",
            "buying_signals": [
                {"signal": "configuration fit", "evidence_quote": "Two BHK around one point one crore all in", "confidence": 0.72},
            ],
            "objections": [
                {"objection": "possession timeline", "evidence_quote": "Before December this year", "severity": "medium"},
                {"objection": "maintenance cost", "evidence_quote": "maintenance also looks higher than Palava", "severity": "medium"},
                {"objection": "loan rate uncertainty", "evidence_quote": "exact loan rate", "severity": "medium"},
                {"objection": "commute concern", "evidence_quote": "Commute to BKC matters", "severity": "medium"},
            ],
            "open_questions": ["possession penalty clause", "ICICI subvention rate", "five-year society outgo"],
            "rep_assessment": f"{first} handled comparison calmly but left finance and legal answers for follow-up.",
            "strengths": ["Acknowledged Palava offer", "Offered peak-hour commute note"],
            "coaching": [{"area": "finance", "recommendation": "Lead next touch with subvention grid and delay clause in one PDF.", "example_moment_ms": 55500}],
            "topics": [{"name": "possession", "weight": 0.32}, {"name": "finance", "weight": 0.28}, {"name": "maintenance", "weight": 0.2}],
            "pivotal": [],
            "next_steps": [{"owner": "rep", "action": "send delay clause, finance grid, and cost comparison", "due_hint": "tomorrow"}],
            "sentiment": {"opening": "skeptical", "middle": "comparing", "closing": "hesitant", "opening_score": 48, "middle_score": 54, "closing_score": 50},
        },
        "f74b1c53-9e50-7d24-c26b-501d0f48b734": {
            "executive_summary": (
                "Sneha queried Powai two BHK sea glimpse pricing versus carpet expectations. "
                "Rep offered festive discount and all-in EMI snapshot; prospect deferred visit pending spouse review."
            ),
            "primary_intent": "price_negotiation",
            "intent_summary": "Location interest with budget stretch; spouse joint decision after document review.",
            "interest_score": 56,
            "conversion_pct": 46,
            "conversion_rationale": "Requested full pricing pack and will call back next week after wife review.",
            "buying_signals": [
                {"signal": "discount openness", "evidence_quote": "up to three lakhs festive benefit", "confidence": 0.58},
            ],
            "objections": [
                {"objection": "carpet vs price", "evidence_quote": "price feels high for the carpet quoted", "severity": "medium"},
                {"objection": "view guarantee", "evidence_quote": "view is guaranteed in writing", "severity": "medium"},
                {"objection": "competitor option", "evidence_quote": "also speaking to Hiranandani", "severity": "medium"},
            ],
            "open_questions": ["floor rise grid", "all-in cost after festive benefit"],
            "rep_assessment": f"{first} offered discount but should lead with all-in sheet earlier in the call.",
            "strengths": ["Asked budget and carpet upfront", "Committed to EMI snapshot"],
            "coaching": [{"area": "pricing", "recommendation": "Open with all-in worksheet before amenity comparison.", "example_moment_ms": 24000}],
            "topics": [{"name": "pricing", "weight": 0.38}, {"name": "view", "weight": 0.26}, {"name": "finance", "weight": 0.18}],
            "pivotal": [],
            "next_steps": [{"owner": "rep", "action": "email view photos, floor rise grid, EMI sheet", "due_hint": "today"}],
            "sentiment": {"opening": "doubtful", "middle": "negotiating", "closing": "undecided", "opening_score": 46, "middle_score": 52, "closing_score": 48},
        },
        "a85c2d64-af61-8e35-d37c-612e1a59c845": {
            "executive_summary": (
                "Pune Kharadi prospect had a hard one crore all-in ceiling with two parking. "
                "Despite exploring compact inventory and Wagholi alternate, EMI cap ended the opportunity."
            ),
            "primary_intent": "budget_mismatch",
            "intent_summary": "Price-capped buyer; no flexibility on two parking or forty thousand EMI ceiling.",
            "interest_score": 34,
            "conversion_pct": 22,
            "conversion_rationale": "Prospect asked to stop repeated calls unless sub ninety five lakh two BHK appears.",
            "buying_signals": [],
            "objections": [
                {"objection": "base price too high", "evidence_quote": "well above my one crore all-in budget", "severity": "high"},
                {"objection": "EMI ceiling", "evidence_quote": "EMI crosses forty thousand", "severity": "high"},
                {"objection": "layout compromise", "evidence_quote": "compact layout may not work", "severity": "medium"},
            ],
            "open_questions": [],
            "rep_assessment": f"{first} explored alternates but qualification on all-in budget could have been earlier.",
            "strengths": ["Surfaced Wagholi alternate honestly"],
            "coaching": [{"area": "qualification", "recommendation": "Confirm all-in cap and parking count in first two minutes.", "example_moment_ms": 16500}],
            "topics": [{"name": "pricing", "weight": 0.52}, {"name": "inventory", "weight": 0.22}],
            "pivotal": [{"start_ms": 99500, "label": "exit signal", "quote": "Please do not call repeatedly", "why_it_matters": "Deal unlikely without new inventory."}],
            "next_steps": [{"owner": "rep", "action": "mark lost-lead with budget criteria", "due_hint": "today"}],
            "sentiment": {"opening": "frustrated", "middle": "firm", "closing": "negative", "opening_score": 36, "middle_score": 30, "closing_score": 20},
        },
        "b96d3e75-b072-9f46-e48d-723f2b6ad956": {
            "executive_summary": (
                "Time-pressed Borivali enquiry turned sour when the rep led with long amenity pitches before price, carpet, "
                "and metro distance. Prospect requested email-only follow-up with exact numbers."
            ),
            "primary_intent": "quick_price_check",
            "intent_summary": "Prospect wanted crisp facts; rep monologues reduced trust and efficiency.",
            "interest_score": 28,
            "conversion_pct": 18,
            "conversion_rationale": "Call ended with email-only directive and explicit dissatisfaction with pitching.",
            "buying_signals": [],
            "objections": [
                {"objection": "vague opening", "evidence_quote": "I asked for starting price, not the full brochure", "severity": "high"},
                {"objection": "metro access unclear", "evidence_quote": "Is metro walking distance or not?", "severity": "high"},
                {"objection": "inefficient call", "evidence_quote": "This call was not efficient — too much pitching", "severity": "high"},
            ],
            "open_questions": ["all-in breakdown on entry stack"],
            "rep_assessment": f"{first} talked too much early; direct answers on price, carpet, and metro came late.",
            "strengths": ["Eventually quoted all-in one point zero six crore"],
            "coaching": [
                {"area": "listening", "recommendation": "Answer price, carpet, metro in the first three turns.", "example_moment_ms": 19000},
                {"area": "pace", "recommendation": "Respect five-minute constraint — bullet facts first.", "example_moment_ms": 0},
            ],
            "topics": [{"name": "pricing", "weight": 0.3}, {"name": "amenities", "weight": 0.28}, {"name": "connectivity", "weight": 0.2}],
            "pivotal": [],
            "next_steps": [{"owner": "rep", "action": "send all-in sheet and metro map", "due_hint": "tonight"}],
            "sentiment": {"opening": "rushed", "middle": "impatient", "closing": "cold", "opening_score": 40, "middle_score": 26, "closing_score": 16},
        },
        "c07e4f86-c183-a057-f59e-834a3c7be067": {
            "executive_summary": (
                "Early-stage Navi Mumbai researcher exploring Ulwe/Panvel for post-monsoon next year. "
                "Rep shared commute, payment sample, and airport/SEZ context without pushing a visit."
            ),
            "primary_intent": "market_research",
            "intent_summary": "Information-only phase; budget forming; October follow-up agreed.",
            "interest_score": 50,
            "conversion_pct": 38,
            "conversion_rationale": "Declined visit; agreed to email pack and October check-in if still active.",
            "buying_signals": [
                {"signal": "accepted overview", "evidence_quote": "Send soft copy only", "confidence": 0.42},
            ],
            "objections": [
                {"objection": "timing", "evidence_quote": "Not buying immediately", "severity": "low"},
                {"objection": "commute filter", "evidence_quote": "Commute to BKC is the main filter", "severity": "medium"},
            ],
            "open_questions": [],
            "rep_assessment": f"{first} set appropriate nurture cadence and respected no-visit boundary.",
            "strengths": ["Qualified timeline without pressure", "Offered planning materials"],
            "coaching": [],
            "topics": [{"name": "location", "weight": 0.32}, {"name": "timeline", "weight": 0.26}, {"name": "payment_plan", "weight": 0.18}],
            "pivotal": [],
            "next_steps": [
                {"owner": "rep", "action": "send commute matrix and sample payment plan", "due_hint": "today"},
                {"owner": "rep", "action": "follow up in October", "due_hint": "Q4"},
            ],
            "sentiment": {"opening": "exploratory", "middle": "neutral", "closing": "polite", "opening_score": 50, "middle_score": 52, "closing_score": 46},
        },
    }


def build_demo_analysis(
    conversation_id: str,
    rep_name: str,
    metrics: dict[str, Any],
    segment_dicts: list[dict[str, Any]],
) -> tuple[PostCallAnalysisResult, dict[str, Any]]:
    first = rep_name.split()[0] if rep_name else "Rep"
    profile = _profiles(first)[conversation_id]
    payload = {
        "executive_summary": profile["executive_summary"],
        "client_intent": {
            "primary_intent": profile["primary_intent"],
            "summary": profile["intent_summary"],
            "interest_score": profile["interest_score"],
            "engagement_level": "high" if profile["interest_score"] >= 70 else "medium" if profile["interest_score"] >= 45 else "low",
            "conversion_likelihood": "high" if profile["conversion_pct"] >= 65 else "medium" if profile["conversion_pct"] >= 45 else "low",
            "conversion_probability_pct": profile["conversion_pct"],
            "conversion_rationale": profile["conversion_rationale"],
            "buying_signals": profile["buying_signals"],
            "objections": profile["objections"],
            "open_questions_unresolved": profile["open_questions"],
        },
        "rep_communication": {
            "overall_assessment": profile["rep_assessment"],
            "talk_listen_ratio": metrics.get("talk_listen_ratio") or {"rep_pct": 50, "prospect_pct": 50},
            "pace_wpm": metrics.get("rep_wpm", 140),
            "filler_rate_pct": metrics.get("rep_filler_rate_pct", 2.0),
            "questions_asked": metrics.get("rep_questions_asked", 0),
            "longest_monologue_sec": metrics.get("longest_rep_monologue_sec", 0),
            "strengths": profile["strengths"],
            "coaching_recommendations": profile["coaching"],
        },
        "topics": profile["topics"],
        "pivotal_moments": profile["pivotal"],
        "next_steps": profile["next_steps"],
        "sentiment_trajectory": profile["sentiment"],
    }
    validated = PostCallAnalysisResult.model_validate(payload)
    validated = apply_computed_metrics(validated, metrics)
    metrics = dict(metrics)
    metrics["call_timeline"] = enrich_call_timeline(
        metrics.get("call_timeline") or {},
        validated,
        segment_dicts,
    )
    finalize_dashboard_metrics(metrics, validated)
    return validated, metrics
