from app.providers.tencent_asr import TencentASRConfigError, TencentASRProvider
from app.core.config import get_settings


def test_realtime_ticket_requires_keys(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tencent_asr_app_id", "")
    monkeypatch.setattr(settings, "tencent_asr_secret_id", "")
    monkeypatch.setattr(settings, "tencent_asr_secret_key", "")
    try:
        TencentASRProvider().realtime_ticket(session_id="s1", voice_id="voice12345678")
        assert False, "expected config error"
    except TencentASRConfigError:
        pass


def test_realtime_ticket_signed_url(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tencent_asr_app_id", "1250000000")
    monkeypatch.setattr(settings, "tencent_asr_secret_id", "AKIDtestSecretId0001")
    monkeypatch.setattr(settings, "tencent_asr_secret_key", "testSecretKey0000000000000000000")
    ticket = TencentASRProvider().realtime_ticket(session_id="s1", voice_id="voiceabcdefgh")
    assert ticket["wss_url"].startswith("wss://asr.cloud.tencent.com/asr/v2/1250000000?")
    assert "signature=" in ticket["wss_url"]
    assert "secretid=AKIDtestSecretId0001" in ticket["wss_url"]
    assert ticket["sample_rate"] == 16000
    assert "secret_key" not in ticket
