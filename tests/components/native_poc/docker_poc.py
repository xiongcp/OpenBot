"""Explicit native Docker CLI qualification; never used as a production executor."""

import hashlib
import io
import json
import platform
import re
import secrets
import subprocess
import tarfile
import time
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[3]


def validate_receipt_tar(raw):
    if len(raw) > 65536:
        raise ValueError("Export byte limit exceeded")
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            members = archive.getmembers()
            if len(members) != 1:
                raise ValueError("Expected one receipt")
            item = members[0]
            if (
                item.name != "receipt"
                or not item.isfile()
                or item.issym()
                or item.islnk()
                or item.size > 4096
                or item.mode & 0o111
            ):
                raise ValueError("Untrusted export metadata")
            stream = archive.extractfile(item)
            if stream is None:
                raise ValueError("Missing receipt")
            data = stream.read(4097)
            if len(data) != item.size:
                raise ValueError("Receipt length mismatch")
            return data
    except tarfile.TarError as exc:
        raise ValueError("Invalid export archive") from exc


class NativeFixture:
    def __init__(self, root, asset):
        self.root = root
        self.image = asset["repo_digest"]
        if not re.fullmatch(r"alpine@sha256:[0-9a-f]{64}", self.image):
            raise ValueError("Only the prepared official image digest may run")
        self.run_id = secrets.token_hex(16)
        self.label = "openbot.native-poc=" + self.run_id
        config = root / "docker-config"
        config.mkdir()
        self.env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(config),
            "DOCKER_CONFIG": str(config),
        }
        self.prefix = [
            "/usr/local/bin/docker",
            "--config",
            str(config),
            "--host",
            "unix:///Users/Zhuanz/.docker/run/docker.sock",
        ]
        self.containers = []
        self.names = []
        self.trace = []
        for name in ["input", "output"]:
            (root / name).mkdir()
        (root / "output").chmod(0o777)
        (root / "input/fixture.txt").write_text("synthetic input\n")
        (root / "input/fixture.txt").chmod(0o644)
        (root / "input").chmod(0o755)

    def cli(self, *args, check=True):
        result = subprocess.run(
            self.prefix + list(args), env=self.env, capture_output=True, timeout=15
        )
        if check and result.returncode:
            raise RuntimeError("Docker fixture command failed: " + result.stderr.decode()[:1000])
        return result

    def inspect(self, identifier):
        return json.loads(self.cli("container", "inspect", identifier).stdout)[0]

    def create(self, role, script):
        name = "openbot-poc-" + self.run_id + "-" + role
        self.names.append(name)
        result = self.cli(
            "container",
            "create",
            "--name",
            name,
            "--label",
            self.label,
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=65532:65532",
            "--memory=64m",
            "--cpus=0.2",
            "--pids-limit=64",
            "--env=HOME=/nonexistent",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
            "--mount",
            f"type=bind,src={self.root / 'input'},dst=/input,readonly",
            "--mount",
            f"type=bind,src={self.root / 'output'},dst=/out",
            "--entrypoint=/bin/sh",
            self.image,
            "-c",
            script,
        )
        identifier = result.stdout.decode().strip()
        if not re.fullmatch(r"[a-f0-9]{64}", identifier):
            raise ValueError("Container ID was not received; recover by registered name/label")
        self.containers.append(identifier)
        self.trace.append({"event": "create", "role": role, "container_id": identifier})
        return identifier

    def run(self, role, script):
        identifier = self.create(role, script)
        self.cli("container", "start", identifier)
        code = int(self.cli("container", "wait", identifier).stdout)
        state = self.inspect(identifier)
        logs = self.cli("container", "logs", identifier)
        return identifier, code, state, (logs.stdout + logs.stderr).decode()[:4096]

    def export(self, identifier):
        if self.inspect(identifier)["State"]["Running"]:
            raise ValueError("Export requires stopped container")
        process = subprocess.Popen(
            self.prefix + ["container", "cp", identifier + ":/out/receipt", "-"],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        try:
            raw = process.stdout.read(65537)
            if len(raw) > 65536:
                raise ValueError("Export stream exceeded limit")
            if process.wait(timeout=5):
                raise ValueError("Export client failed")
            return validate_receipt_tar(raw)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            process.stdout.close()

    def cleanup(self):
        # Names are registered before create; check ownership even if the client lost its receipt.
        for name in self.names:
            found = self.cli("container", "inspect", name, check=False)
            if found.returncode:
                continue
            item = json.loads(found.stdout)[0]
            if item["Config"]["Labels"].get("openbot.native-poc") != self.run_id:
                raise ValueError("Refuse to touch a container owned by someone else")
            identifier = item["Id"]
            if item["State"]["Running"]:
                self.cli("container", "stop", "--time=1", identifier)
            self.cli("container", "wait", identifier)
            self.cli("container", "rm", identifier)
            self.trace.append({"event": "remove", "container_id": identifier})
        return (
            self.cli(
                "container", "ls", "-a", "--filter", "label=" + self.label, "--format", "{{.ID}}"
            )
            .stdout.decode()
            .split()
        )


def run_poc():
    if (platform.system(), platform.machine()) != ("Darwin", "arm64"):
        raise ValueError("This is the macOS ARM64 Docker Desktop combination only")
    asset = json.loads((ROOT / "components/assets/alpine-native-poc.json").read_text())
    with TemporaryDirectory(prefix="openbot-native-") as directory:
        fixture = NativeFixture(Path(directory), asset)
        report = {
            "scope": "native CLI primitives only; not production worker qualification",
            "platform": [platform.system(), platform.machine()],
            "image": asset,
            "checks": {},
            "trace": fixture.trace,
        }
        try:
            base_script = """
set -eu
test "$(id -u)" = 65532
test "$HOME" = /nonexistent
test ! -e /var/run/docker.sock
test -z "${OPENAI_API_KEY-}${AWS_SECRET_ACCESS_KEY-}${LARK_APP_SECRET-}"
test "$(cat /input/fixture.txt)" = 'synthetic input'
if touch /input/blocked 2>/dev/null; then exit 21; fi
if touch /blocked 2>/dev/null; then exit 22; fi
test -z "$(ip route)"
test ! -e /sys/class/net/eth0
test "$(cat /sys/fs/cgroup/memory.max)" = 67108864
test "$(cat /sys/fs/cgroup/pids.max)" = 64
printf 'synthetic receipt\n' > /out/receipt
cat /etc/alpine-release
cat /lib/apk/db/installed
"""
            identifier, code, info, logs = fixture.run("bounds", base_script)
            assert code == 0, logs
            host = info["HostConfig"]
            assert host["ReadonlyRootfs"] and host["NetworkMode"] == "none"
            assert host["Memory"] == 67108864 and host["PidsLimit"] == 64
            assert host["NanoCpus"] == 200_000_000 and host["CapDrop"] == ["ALL"]
            assert info["Config"]["User"] == "65532:65532"
            assert fixture.export(identifier) == b"synthetic receipt\n"
            report["checks"]["readonly_and_no_network"] = True
            report["asset_package_metadata"] = logs
            (fixture.root / "output/receipt").unlink()
            live = fixture.create(
                "lifecycle",
                "set -e; printf 'synthetic receipt\\n' > /out/receipt; "
                "trap 'exit 0' TERM; while :; do sleep 1; done",
            )
            client = subprocess.Popen(
                fixture.prefix + ["container", "start", "--attach", live],
                env=fixture.env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                for _ in range(60):
                    if fixture.inspect(live)["State"]["Running"]:
                        break
                    time.sleep(0.05)
                assert fixture.inspect(live)["State"]["Running"]
                client.kill()
                client.wait(timeout=5)
                assert fixture.inspect(live)["State"]["Running"]
                report["checks"]["client_exit_does_not_stop_container"] = True
                fixture.trace.append(
                    {
                        "event": "client_killed_container_still_running",
                        "client_pid": client.pid,
                        "container_id": live,
                    }
                )
                fixture.cli("container", "stop", "--time=2", live)
                fixture.trace.append({"event": "stop", "container_id": live})
                fixture.cli("container", "wait", live)
                fixture.trace.append({"event": "wait", "container_id": live})
                assert fixture.export(live) == b"synthetic receipt\n"
                fixture.trace.append({"event": "validated_export", "container_id": live})
            finally:
                if client.poll() is None:
                    client.kill()
                    client.wait(timeout=5)
            _, exit_code, memory, _ = fixture.run(
                "memory", "awk 'BEGIN{s=\"x\";for(i=0;i<27;i++) s=s s;print length(s)}'"
            )
            report["memory_observation"] = {
                "exit_code": exit_code,
                "oom_killed": memory["State"]["OOMKilled"],
            }
            assert exit_code != 0 and memory["State"]["OOMKilled"]
            report["checks"]["memory_limit_enforced"] = True
            _, exit_code, _, logs = fixture.run(
                "pids", "i=0; while [ $i -lt 80 ]; do sleep 10 & i=$((i+1)); done; wait"
            )
            assert exit_code != 0 and "fork" in logs.lower()
            report["checks"]["pids_limit_enforced"] = True
            report["export_sha256"] = hashlib.sha256(b"synthetic receipt\n").hexdigest()
        finally:
            report["remaining_owned_containers"] = fixture.cleanup()
            (ROOT / "evidence/implementation/native-container-attempt.json").write_text(
                json.dumps(report, indent=2) + "\n"
            )
        assert not report["remaining_owned_containers"]
        report["checks"]["stop_wait_export_remove"] = True
        return report
