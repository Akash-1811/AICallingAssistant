"""Multichannel Results parsing: physical channel = speaker (0 = mic/rep, 1 = tab/customer)."""

from app.live.call_recorder import resolve_lead_speaker_id, speaker_role
from app.live.deepgram_service import _segment_from_results, _speaker_channel
from app.storage.call_store import Conversation


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


def test_speaker_role_maps_lead_channel_to_prospect():
    assert speaker_role(speaker_id=1, lead_speaker_id=1) == "prospect"
    assert speaker_role(speaker_id=0, lead_speaker_id=1) == "rep"


def test_speaker_role_is_unknown_before_a_lead_is_established():
    # First segment of a call can race the session_status update that sets
    # the lead — safer to say "unknown" than to guess wrong.
    assert speaker_role(speaker_id=0, lead_speaker_id=None) == "unknown"
    assert speaker_role(speaker_id=1, lead_speaker_id=None) == "unknown"


def test_resolve_lead_speaker_id_does_not_wait_on_two_channel_calls():
    # The very first segment saved for a call can race the session_status
    # update that would otherwise set lead_speaker_id — but for a real
    # two-channel call there's nothing to wait for, channel 1 is always
    # the customer, so this must not fall back to "unknown".
    row = Conversation(id="c1", audio_channels=2, lead_speaker_id=None)
    assert resolve_lead_speaker_id(row) == 1


def test_resolve_lead_speaker_id_respects_stored_value_once_set():
    row = Conversation(id="c1", audio_channels=2, lead_speaker_id=1)
    assert resolve_lead_speaker_id(row) == 1


def test_resolve_lead_speaker_id_has_no_answer_for_genuine_single_channel():
    row = Conversation(id="c1", audio_channels=1, lead_speaker_id=None)
    assert resolve_lead_speaker_id(row) is None
