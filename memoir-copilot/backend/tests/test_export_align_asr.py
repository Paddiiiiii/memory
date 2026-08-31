from app.services.audio.alignment import cross_correlate_offset, estimate_from_sync_peaks, watch_to_pc_ms
from app.services.export.formats import segments_to_srt, segments_to_vtt
from app.services.transcription.dual_asr import compare_block, tokenize_zh


def test_srt_basic():
    srt = segments_to_srt(
        [
            {
                "speaker_id": "s0",
                "start_ms": 0,
                "end_ms": 1500,
                "raw_text": "你好",
            }
        ],
        speaker_names={"s0": "老人"},
    )
    assert "00:00:00,000 --> 00:00:01,500" in srt
    assert "老人: 你好" in srt


def test_vtt_header():
    vtt = segments_to_vtt([{"speaker_id": "a", "start_ms": 1000, "end_ms": 2000, "raw_text": "嗯"}])
    assert vtt.startswith("WEBVTT")


def test_alignment_sync():
    r = estimate_from_sync_peaks(
        pc_start_ms=1000,
        pc_end_ms=361000,
        watch_start_ms=1500,
        watch_end_ms=361800,
    )
    assert abs(r.clock_ratio - 1.0) < 0.01
    pc = watch_to_pc_ms(1500, ratio=r.clock_ratio, start_offset_ms=r.start_offset_ms)
    assert abs(pc - 1000) < 1.0


def test_dual_asr_confirmed():
    v = compare_block("我六九年去了武汉", "我六九年去了武汉")
    assert v.status == "CONFIRMED"


def test_dual_asr_disputed():
    v = compare_block("我六九年去了武昌", "我六九年去了武汉")
    assert v.status == "DISPUTED"


def test_tokenize():
    assert "武汉" in "".join(tokenize_zh("去武汉工作"))


def test_ncc_identical():
    lag, score = cross_correlate_offset([1, 2, 3, 2, 1], [1, 2, 3, 2, 1])
    assert lag == 0
    assert score > 0.9
