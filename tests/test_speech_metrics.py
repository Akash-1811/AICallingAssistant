"""Tests for deterministic post-call speech metrics."""

from app.analysis.speech_metrics import compute_speech_metrics


def test_talk_ratio_from_timestamps():
    segments = [
        {
            "speaker_id": 0,
            "role": "rep",
            "text": "Hello thanks for calling today.",
            "word_count": 5,
            "start_ms": 0,
            "end_ms": 5000,
        },
        {
            "speaker_id": 1,
            "role": "prospect",
            "text": "I want pricing for a three BHK apartment downtown.",
            "word_count": 9,
            "start_ms": 5000,
            "end_ms": 15000,
        },
    ]
    metrics = compute_speech_metrics(segments, [], lead_speaker_id=1)
    ratio = metrics["talk_listen_ratio"]
    assert ratio["rep_pct"] == 33
    assert ratio["prospect_pct"] == 67
    assert metrics["metrics_quality"] == "full"
    assert metrics["rep_questions_asked"] == 0


def test_rep_questions_and_fillers():
    segments = [
        {
            "speaker_id": 0,
            "role": "rep",
            "text": "Um what is your budget and timeline?",
            "word_count": 7,
            "start_ms": 0,
            "end_ms": 4000,
        },
        {
            "speaker_id": 1,
            "role": "prospect",
            "text": "Around two crore by December.",
            "word_count": 5,
            "start_ms": 4000,
            "end_ms": 7000,
        },
    ]
    metrics = compute_speech_metrics(segments, [], lead_speaker_id=1)
    assert metrics["rep_questions_asked"] == 1
    assert metrics["rep_filler_rate_pct"] > 0
    assert metrics["turn_count"] == 2


def test_call_timeline_buckets_from_transcript():
    segments = [
        {
            "speaker_id": 0,
            "role": "rep",
            "text": "Hello, what is your budget?",
            "word_count": 5,
            "start_ms": 0,
            "end_ms": 8000,
        },
        {
            "speaker_id": 1,
            "role": "prospect",
            "text": "Around two crore. I am worried about maintenance charges though.",
            "word_count": 10,
            "start_ms": 8000,
            "end_ms": 20000,
        },
        {
            "speaker_id": 0,
            "role": "rep",
            "text": "We can share the maintenance breakup on email.",
            "word_count": 8,
            "start_ms": 20000,
            "end_ms": 28000,
        },
    ]
    metrics = compute_speech_metrics(segments, [], lead_speaker_id=1)
    timeline = metrics["call_timeline"]
    assert timeline["duration_ms"] == 28000
    assert len(timeline["buckets"]) == 16
    active = [b for b in timeline["buckets"] if b["rep_words"] or b["prospect_words"]]
    assert len(active) >= 2
    assert any(b["prospect_words"] > 0 for b in timeline["buckets"])
    assert any(b["rep_talk_pct"] > 0 for b in timeline["buckets"])


def test_prospect_questions_and_call_glance():
    segments = [
        {
            "speaker_id": 0,
            "role": "rep",
            "text": "What is your budget?",
            "word_count": 4,
            "start_ms": 0,
            "end_ms": 4000,
        },
        {
            "speaker_id": 1,
            "role": "prospect",
            "text": "Around two crore?",
            "word_count": 3,
            "start_ms": 4000,
            "end_ms": 8000,
        },
        {
            "speaker_id": 1,
            "role": "prospect",
            "text": "What about maintenance charges?",
            "word_count": 4,
            "start_ms": 8000,
            "end_ms": 12000,
        },
    ]
    metrics = compute_speech_metrics(segments, [], lead_speaker_id=1)
    assert metrics["rep_questions_asked"] == 1
    assert metrics["prospect_questions_asked"] == 2
    assert metrics["total_questions_asked"] == 3

    from app.analysis.speech_metrics import build_call_glance, downsample_bucket_series

    glance = build_call_glance(metrics)
    assert glance["total_duration_sec"] == 12
    assert glance["questions_asked"] == 3

    curves = downsample_bucket_series(metrics["call_timeline"]["buckets"], "sentiment_score")
    assert len(curves) == 5
    assert curves[0]["label"] == "Start"
    assert curves[-1]["label"] == "End"


def test_engagement_curves_are_measured_only():
    """Curves must come from transcript measurements — no synthetic sentiment/interest."""
    from app.analysis.speech_metrics import build_engagement_curves, compute_speech_metrics

    segments = [
        {"speaker_id": 0, "role": "rep", "text": "What is your budget for the flat?",
         "word_count": 7, "start_ms": 0, "end_ms": 4000},
        {"speaker_id": 1, "role": "prospect", "text": "Around two crore, where is it located?",
         "word_count": 7, "start_ms": 4000, "end_ms": 9000},
    ]
    metrics = compute_speech_metrics(segments, [], lead_speaker_id=1)

    buckets = metrics["call_timeline"]["buckets"]
    assert all("sentiment_score" not in b and "interest_score" not in b for b in buckets)

    curves = build_engagement_curves(metrics["call_timeline"])
    assert set(curves) == {"prospect_talk", "prospect_questions", "objections"}
    assert all(len(series) == 5 for series in curves.values())


def test_question_detection_is_multilingual():
    """Hindi questions (Devanagari or romanized, with or without '?') must count."""
    from app.analysis.speech_metrics import is_question_sentence

    assert is_question_sentence("What is your budget?") is True
    assert is_question_sentence("क्या आपके पास 3BHK है")
    assert is_question_sentence("Kitna price hai iska")
    assert is_question_sentence("कहाँ पर स्थित है यह प्रोजेक्ट")
    assert is_question_sentence("हमें यह प्रोजेक्ट पसंद आया।") is False
    assert is_question_sentence("Thanks for calling.") is False
