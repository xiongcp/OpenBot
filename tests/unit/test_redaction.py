import base64
import urllib.parse

import pytest
from openbot.observability.redaction import (
    RedactionPipeline,
    StreamingSecretRedactor,
)


def test_arbitrary_chunk_boundaries_long_secrets_encodings_and_allowlist_injection():
    short_canary = "sk_live_canary_9876543210abcdef"
    # 300-byte secret exceeding any naive 128-byte fixed window
    long_canary = "wk_long_secret_" + ("A1b2C3d4" * 36)
    assert len(long_canary) > 256

    for secret in (short_canary, long_canary):
        text = f"prefix {secret} middle # pragma: allowlist secret {secret} suffix"
        # Split at every single character index to prove arbitrary chunk boundary safety
        for split_at in range(1, len(text)):
            stream = StreamingSecretRedactor(registered_secrets=(short_canary, long_canary))
            out = stream.feed(text[:split_at]) + stream.feed(text[split_at:]) + stream.flush()
            assert secret not in out
            assert "[REDACTED]" in out

    # Base64 and URL-encoded variants of registered secrets are also redacted
    b64_val = base64.b64encode(short_canary.encode()).decode()
    url_val = urllib.parse.quote(short_canary + "/+=extra", safe="")
    stream_enc = StreamingSecretRedactor(
        registered_secrets=(short_canary, short_canary + "/+=extra")
    )
    encoded_payload = f"b64={b64_val} url={url_val} # pragma: allowlist secret"
    redacted_enc = stream_enc.feed(encoded_payload) + stream_enc.flush()
    assert b64_val not in redacted_enc
    assert url_val not in redacted_enc
    assert short_canary not in redacted_enc


def test_all_sinks_classification_preservation_and_online_verification_forbidden():
    canary = "fs_sec_canary_sink_test_123456"
    pipeline = RedactionPipeline(registered_secrets=(canary,))
    contract = pipeline.contract()
    assert contract.network_verification_enabled is False
    assert contract.external_allowlist_honored is False
    assert contract.guarantees_100_percent_detection is False
    assert contract.negative_scan_downgrades_classification is False

    # 1. Cover stdout, stderr, sdk_debug, exception, header, ui_event, artifact, diag, model_input
    for sink in (
        "stdout",
        "stderr",
        "sdk_debug",
        "exception",
        "http_header",
        "ui_event",
        "artifact",
        "diagnostic",
        "model_input",
    ):
        res = pipeline.sanitize_sink(
            sink=sink,
            text=f'{{"err":"failed with {canary} and Bearer sk-proj-1234567890abcdefghij"}}',
            data_class="SENSITIVE",
        )
        assert canary not in res.sanitized_text
        assert "sk-proj-1234567890abcdefghij" not in res.sanitized_text
        assert res.data_class == "SENSITIVE"

    # 2. Negative scan result NEVER downgrades SECRET or SENSITIVE classification
    clean_res = pipeline.sanitize_sink(
        sink="artifact",
        text="harmless looking text without regex hits",
        data_class="SECRET",
    )
    assert clean_res.redaction_count == 0
    assert clean_res.data_class == "SECRET"
    assert clean_res.allow_remote_egress is False

    # 3. Uncertain sensitive content or attempt to enable online verifier is refused
    uncertain = pipeline.sanitize_sink(
        sink="model_input",
        text="binary/opaque blob",
        data_class="WORKSPACE",
        uncertain_sensitivity=True,
    )
    assert uncertain.allow_remote_egress is False

    with pytest.raises(PermissionError, match="Network verification"):
        pipeline.verify_secret_online_forbidden(canary)
