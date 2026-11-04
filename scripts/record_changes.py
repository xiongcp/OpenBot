"""Create review artifacts without staging the user's untracked design package."""

import difflib
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def reconstructed(path, text):
    if path == "README.md":
        lines = [
            line for line in text.split("\n") if not line.startswith(("实施进度：", "本地验证："))
        ]
        return "\n".join(lines).replace("\n\n\n\n本包", "\n\n本包")
    if path == "tasks/backlog.json":
        tasks = json.loads(text)
        for task in tasks:
            task["status"] = "TODO"
            task.pop("execution", None)
        return json.dumps(tasks, ensure_ascii=False, indent=2) + "\n"
    if path == "tasks/TASKS.md":
        return re.sub(r"(阶段 [^\n]+? · 状态 )[A-Z_]+", r"\1TODO", text).replace(
            "初始为TODO，当前状态与证据随实施同步", "全部初始状态TODO"
        )
    return None


def run():
    initial = json.loads((ROOT / "evidence/implementation/initial-files.json").read_text())
    roots = [
        "services/core/src",
        "services/feishu_gateway/src",
        "native/supervisor",
        "packaging",
        "evals",
        "release",
        "contracts/schemas",
        "tests",
        "scripts",
        "docs",
        "db/migrations",
        ".github",
        "components/admissions",
        "components/source-reuse",
        "components/locks",
        "components/assets",
        "evidence/implementation",
    ]
    files = {
        path
        for name in roots
        for path in (ROOT / name).rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not set(path.parts) & {"__pycache__"}
        and not any(part.endswith(".egg-info") for part in path.parts)
    }
    files.update(
        ROOT / name
        for name in [
            "README.md",
            "SECURITY.md",
            "tasks/backlog.json",
            "tasks/TASKS.md",
            "validation/verify_design.py",
            ".gitignore",
            ".python-version",
            "pyproject.toml",
            "uv.lock",
            "THIRD_PARTY_NOTICES.md",
            "task_plan.md",
            "findings.md",
            "progress.md",
            "contracts/proposal-storage.md",
        ]
    )
    records, patch = [], []
    for path in sorted(files):
        name = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        before_hash = initial.get(name)
        if before_hash == digest(raw):
            continue
        entry = {"path": name, "before_sha256": before_hash, "after_sha256": digest(raw)}
        is_source = path.suffix in {".py", ".toml", ".yml", ".sql", ".md", ".json", ".lock"}
        omitted = name.startswith(("evidence/", "components/locks/"))
        entry["included_in_patch"] = is_source and not omitted
        if entry["included_in_patch"]:
            text = raw.decode("utf-8")
            before = reconstructed(name, text) if before_hash else ""
            if before is None or before_hash and digest(before.encode()) != before_hash:
                entry["included_in_patch"] = False
                entry["omission_reason"] = (
                    "Original bytes not retained; review current file and hash"
                )
            else:
                patch.extend(
                    difflib.unified_diff(
                        before.splitlines(keepends=True),
                        text.splitlines(keepends=True),
                        fromfile="a/" + name if before_hash else "/dev/null",
                        tofile="b/" + name,
                    )
                )
        records.append(entry)
    output = ROOT / "reports"
    (output / "implementation.diff").write_text("".join(patch))
    report = {
        "scope": "Review artifact, not a baseline commit or complete apply-ready repository patch",
        "omitted_artifacts": (
            "Raw logs/licenses/lock snapshots are indexed by hash; source and three "
            "hash-verified original reconstructions included"
        ),
        "files": records,
    }
    (output / "implementation-changes.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {"changed_or_new": len(records), "patch_bytes": sum(len(x.encode()) for x in patch)}
        )
    )


if __name__ == "__main__":
    run()
