"""Controlled container sandbox broker, ownership ledger, and stop/wait/export/remove order."""

import io
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

QUALIFIED_CONTAINER_BACKENDS = frozenset({"docker_cli"})


@dataclass(frozen=True, slots=True)
class ContainerOwnership:
    profile_id: str
    operation_id: str
    attempt_id: str
    runtime_epoch: str

    def labels(self) -> dict[str, str]:
        return {
            "openbot.profile_id": self.profile_id,
            "openbot.operation_id": self.operation_id,
            "openbot.attempt_id": self.attempt_id,
            "openbot.runtime_epoch": self.runtime_epoch,
        }


class DockerEnginePort(Protocol):
    def create(self, name: str, labels: dict[str, str], argv: tuple[str, ...]) -> str: ...
    def start(self, cid: str) -> int: ...
    def inspect(self, cid_or_name: str) -> dict[str, Any] | None: ...
    def stop(self, cid: str) -> None: ...
    def wait(self, cid: str) -> int: ...
    def export_tar(self, cid: str) -> bytes: ...
    def remove(self, cid: str) -> None: ...


def validate_and_extract_tar_export(
    raw_tar: bytes,
    *,
    max_archive_bytes: int = 65_536,
    max_file_bytes: int = 16_384,
    max_files: int = 16,
) -> dict[str, bytes]:
    """Validate exported tar stream and reject symlinks, traversal, devices, or executable bits."""
    if len(raw_tar) > max_archive_bytes:
        raise PermissionError("Exported tar stream exceeds max_archive_bytes")
    extracted: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(raw_tar), mode="r:") as archive:
            members = archive.getmembers()
            if not members or len(members) > max_files:
                raise PermissionError("Exported tar archive member count out of bounds")
            for item in members:
                if (
                    not item.name
                    or item.name.startswith("/")
                    or ".." in item.name.split("/")
                    or "\\" in item.name
                ):
                    raise PermissionError(f"Untrusted export path in tar: {item.name}")
                if (
                    not item.isfile()
                    or item.issym()
                    or item.islnk()
                    or item.ischr()
                    or item.isblk()
                    or item.isfifo()
                ):
                    raise PermissionError(
                        f"Symlink, hardlink, or special file refused: {item.name}"
                    )
                if item.size < 0 or item.size > max_file_bytes:
                    raise PermissionError(f"Exported file size out of bounds: {item.name}")
                if item.mode & 0o111:
                    raise PermissionError(f"Executable mode bit refused on export: {item.name}")
                stream = archive.extractfile(item)
                if stream is None:
                    raise PermissionError(f"Missing stream for tar member: {item.name}")
                data = stream.read(max_file_bytes + 1)
                if len(data) != item.size:
                    raise PermissionError(f"Exported member length mismatch: {item.name}")
                extracted[item.name] = data
    except tarfile.TarError as exc:
        raise PermissionError("Malformed export tar archive") from exc
    return extracted


class ContainerSandboxBroker:
    """Manage non-root isolated containers with independent lifecycle and strict export order."""

    def __init__(
        self,
        *,
        engine: DockerEnginePort,
        backend_name: str,
        backend_qualified: bool,
        profile_id: str,
        pinned_image: str,
    ) -> None:
        if backend_name not in QUALIFIED_CONTAINER_BACKENDS or not backend_qualified:
            raise PermissionError(
                f"CAPABILITY_UNAVAILABLE: container backend '{backend_name}' is not qualified; "
                "automatic fallback to Podman/nerdctl/bubblewrap/host is forbidden"
            )
        if not re.fullmatch(r"[a-z0-9._/-]+@sha256:[0-9a-f]{64}", pinned_image):
            raise PermissionError("Pinned repo@sha256:... image digest is required")
        self._engine = engine
        self._profile_id = profile_id
        self._pinned_image = pinned_image
        self._registered: dict[str, ContainerOwnership] = {}
        self._reclaimed: set[str] = set()

    def build_create_argv(
        self,
        *,
        container_name: str,
        ownership: ContainerOwnership,
        input_dir: Path,
        output_dir: Path,
        host_home: Path,
        command: tuple[str, ...],
        memory_limit: str = "64m",
        cpus_limit: str = "0.2",
        pids_limit: int = 64,
    ) -> tuple[str, ...]:
        if ownership.profile_id != self._profile_id:
            raise PermissionError("Ownership profile_id mismatch")
        resolved_home = host_home.resolve()
        for p in (input_dir, output_dir):
            s = str(p)
            if "docker.sock" in s:
                raise PermissionError(
                    "Mounting docker.sock inside untrusted container is forbidden"
                )
            rp = p.resolve()
            if rp == resolved_home or rp.is_relative_to(resolved_home):
                raise PermissionError("Mounting host HOME into container is forbidden")

        label_args: list[str] = []
        for k, v in sorted(ownership.labels().items()):
            label_args.extend(["--label", f"{k}={v}"])

        # Never include --rm so evidence is exported before explicit container removal
        return (
            "container",
            "create",
            "--name",
            container_name,
            *label_args,
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=65532:65532",
            f"--memory={memory_limit}",
            f"--cpus={cpus_limit}",
            f"--pids-limit={pids_limit}",
            "--env=HOME=/nonexistent",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
            "--mount",
            f"type=bind,src={input_dir.resolve()},dst=/input,readonly",
            "--mount",
            f"type=bind,src={output_dir.resolve()},dst=/out",
            self._pinned_image,
            *command,
        )

    def launch(
        self,
        *,
        ownership: ContainerOwnership,
        input_dir: Path,
        output_dir: Path,
        host_home: Path,
        command: tuple[str, ...],
    ) -> tuple[str, int]:
        cname = f"openbot-{ownership.attempt_id}"
        argv = self.build_create_argv(
            container_name=cname,
            ownership=ownership,
            input_dir=input_dir,
            output_dir=output_dir,
            host_home=host_home,
            command=command,
        )
        cid = self._engine.create(cname, ownership.labels(), argv)
        self._registered[cid] = ownership
        client_pid = self._engine.start(cid)
        return cid, client_pid

    def notify_client_exited(self, cid: str, client_pid: int) -> None:
        # Client exit NEVER marks the container stopped or reclaimed!
        del cid, client_pid

    def is_reclaimed(self, cid: str) -> bool:
        return cid in self._reclaimed

    def _verify_ownership(self, cid: str) -> dict[str, Any]:
        info = self._engine.inspect(cid)
        if info is None:
            raise PermissionError(f"Container not found: {cid}")
        labels = info.get("Labels") or {}
        if cid not in self._registered or labels.get("openbot.profile_id") != self._profile_id:
            raise PermissionError(
                f"Refusing to operate on unregistered or foreign container: {cid}"
            )
        return info

    def export_verified_files(self, cid: str) -> dict[str, bytes]:
        info = self._verify_ownership(cid)
        if info.get("Running") or not info.get("WaitConfirmed"):
            raise PermissionError(
                "Container is still Running or wait() not confirmed; export refused"
            )
        raw_tar = self._engine.export_tar(cid)
        return validate_and_extract_tar_export(raw_tar)

    def stop_wait_export_and_remove(self, cid: str) -> tuple[dict[str, bytes], bool]:
        info = self._verify_ownership(cid)
        if info.get("Running"):
            self._engine.stop(cid)
        self._engine.wait(cid)
        exported = self.export_verified_files(cid)
        self._engine.remove(cid)
        self._reclaimed.add(cid)
        return exported, True
