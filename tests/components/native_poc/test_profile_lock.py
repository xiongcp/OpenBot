import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.name != "posix", reason="Native flock probe; Windows is NOT_RUN")
def test_single_supervisor_lock_survives_client_disconnect_and_releases_after_kill(tmp_path):
    code = """
import fcntl,sys
with open(sys.argv[1], "a+") as handle:
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(23)
    print("ready", flush=True)
    sys.stdin.read()
"""
    args = [sys.executable, "-c", code, str(tmp_path / "profile.lock")]
    owner = subprocess.Popen(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        assert owner.stdout.readline().strip() == "ready"
        contender = subprocess.run(args, input="", capture_output=True, text=True, timeout=5)
        assert contender.returncode == 23
        client = subprocess.run(
            [sys.executable, "-c", "print('client disconnected')"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert client.returncode == 0
        assert owner.poll() is None
        owner.kill()
        owner.wait(timeout=5)
        next_owner = subprocess.run(args, input="", capture_output=True, text=True, timeout=5)
        assert next_owner.returncode == 0
        assert next_owner.stdout.strip() == "ready"
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait(timeout=5)
        owner.stdin.close()
        owner.stdout.close()
        owner.stderr.close()
