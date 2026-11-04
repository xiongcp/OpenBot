from pathlib import Path

from openbot.application.macos_gate import MacOSNativePlatformGate


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
