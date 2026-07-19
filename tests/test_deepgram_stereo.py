"""Multichannel Results parsing: physical channel = speaker (0 = mic/rep, 1 = tab/customer)."""

from app.live.deepgram_service import _segment_from_results, _speaker_channel


def _results(channel_index, transcript, words=None):
    return {
        "type": "Results",
        "is_final": True,
        "channel_index": channel_index,
        "channel": {"alternatives": [{"transcript": transcript, "words": words or []}]},
    }


def test_speaker_channel_reads_streaming_channel_index_list():
    # Live API sends channel_index as [channel, total_channels].
    assert _speaker_channel({"channel_index": [1, 2]}) == 1
    assert _speaker_channel({"channel_index": [0, 2]}) == 0


def test_speaker_channel_defaults_to_mic_on_malformed_payload():
    assert _speaker_channel({}) == 0
    assert _speaker_channel({"channel_index": "bad"}) == 0


def test_segment_carries_channel_speaker_and_word_timestamps():
    payload = _results(
        [1, 2],
        "What is the price?",
        words=[
            {"word": "What", "start": 1.0, "end": 1.2},
            {"word": "price", "start": 1.8, "end": 2.1},
        ],
    )
    seg = _segment_from_results(payload)
    assert seg is not None
    assert seg.speaker == 1
    assert seg.text == "What is the price?"
    assert seg.start_ms == 1000
    assert seg.end_ms == 2100


def test_empty_transcript_yields_no_segment():
    assert _segment_from_results(_results([0, 2], "")) is None
    assert _segment_from_results(_results([0, 2], "   ")) is None


def test_segment_without_words_has_no_timestamps():
    seg = _segment_from_results(_results([0, 2], "Hello there"))
    assert seg is not None
    assert seg.speaker == 0
    assert seg.start_ms is None and seg.end_ms is None
