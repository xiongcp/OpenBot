from pathlib import Path

from openbot.application.macos_gate import MacOSNativePlatformGate
from openbot.policy.secrets.broker import MacOSKeychainCliBackend


def test_macos_native_gate_verifies_arm64_without_claiming_intel_or_screen_recording(
    tmp_path: Path,
) -> None:
    gate = MacOSNativePlatformGate(tmp_path / "macos_gate")
    report = gate.run_native_checks()
    assert report.os_name == "Darwin"
    assert report.arch == "arm64"
    assert report.filesystem_and_symlink_verified is True
    assert report.keychain_compartment_verified is True
    assert report.user_daemon_manifest_verified is True
    assert report.browser_profile_and_worker_reclaim_verified is True
    assert report.intel_x86_64_verified is False
    assert report.screen_recording_permission_requested is False
    assert report.claims_desktop_gui_control_enabled is False
    assert report.evidence_kind == "NATIVE_OS"
    assert report.qualification_status == "PASS"

    # Synthetic checks are explicitly labeled SYNTHETIC_CONTRACT and cannot claim native pass
    syn = gate.run_synthetic_checks()
    assert syn.evidence_kind == "SYNTHETIC_CONTRACT"
    assert syn.qualification_status == "SYNTHETIC_ONLY"

    # Unsupported OS/arch or broken Keychain binary must report BLOCKED_ENV, never PASS
    blocked_os = gate.run_native_checks(os_override=("Linux", "x86_64"))
    assert blocked_os.qualification_status == "BLOCKED_ENV"
    assert blocked_os.keychain_compartment_verified is False

    broken_kc = MacOSKeychainCliBackend(
        service_name="com.openbot.qa.broken", security_binary="/nonexistent/security"
    )
    blocked_kc = gate.run_native_checks(keychain_backend=broken_kc)
    assert blocked_kc.qualification_status == "BLOCKED_ENV"
    assert blocked_kc.keychain_compartment_verified is False
