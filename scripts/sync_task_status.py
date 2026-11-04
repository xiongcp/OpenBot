"""Keep readable task-card states synchronized without rewriting the design cards."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run():
    tasks = {t["id"]: t for t in json.loads((ROOT / "tasks/backlog.json").read_text())}
    path = ROOT / "tasks/TASKS.md"
    source = path.read_text()
    found = set()

    def update(match):
        task_id, section = match.group(1), match.group(0)
        found.add(task_id)
        result, count = re.subn(
            r"(阶段 [^\n]+? · 状态 )[A-Z_]+",
            lambda state: state.group(1) + tasks[task_id]["status"],
            section,
            count=1,
        )
        if count != 1:
            raise ValueError("Missing readable state for " + task_id)
        return result

    result = re.sub(r"(?ms)^### (OB-\d{3})\n.*?(?=^### OB-|\Z)", update, source)
    if found != set(tasks):
        raise ValueError("Task card ID mismatch")
    path.write_text(result)
    print(f"Synchronized {len(found)} task-card states")


if __name__ == "__main__":
    run()
