import json
import subprocess
import sys
import unittest


class BootstrapTests(unittest.TestCase):
    def test_version_and_health_do_not_start_a_daemon(self):
        from openbot.cli import main

        self.assertEqual(main(["version"]), 0)
        self.assertEqual(main(["health"]), 0)

    def test_import_has_no_network_or_child_process(self):
        script = """
import sys
def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
        raise RuntimeError(event)
sys.addaudithook(audit)
import openbot
import openbot.domain
import openbot.cli
print("clean")
"""
        result = subprocess.run(
            [sys.executable, "-c", script], text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "clean")

    def test_cli_health_reports_unimplemented_capabilities(self):
        result = subprocess.run(
            [sys.executable, "-m", "openbot", "health"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        health = json.loads(result.stdout)
        self.assertFalse(health["daemon_running"])
        self.assertEqual(health["isolation"], "CAPABILITY_UNAVAILABLE")
