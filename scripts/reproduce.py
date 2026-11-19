"""Run from an extracted reproduction package; deliberately never calls an LLM."""

import json
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "src"))
os.environ["YANJI_RUNTIME"] = str(root / "reproduced")

from yanji import db
from yanji.skills.analysis import execute
from yanji.skills.context import Context


def main():
    db.initialize()
    manifest = json.loads((root / "manifest.json").read_text())
    report = manifest["report"]
    pid = report["project_id"]
    with db.session() as session:
        session.merge(db.Record(id=pid, kind="project", data={"name": report["title"]}))
        for d in json.loads((root / "datasets.json").read_text()):
            target = Path(os.environ["YANJI_RUNTIME"]) / "inputs" / d["id"]
            target.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copy2(root / "inputs" / d["id"] / "matrix.json.gz", target / "matrix.json.gz")
            payload = {
                k: v
                for k, v in d.items()
                if k not in {"id", "kind", "project_id", "created_at", "updated_at"}
            }
            payload["storage"] = str(target.relative_to(Path(os.environ["YANJI_RUNTIME"])))
            session.merge(db.Record(id=d["id"], kind="dataset", project_id=pid, data=payload))
    outputs = []
    for step in manifest["plan"]["steps"]:
        if step["skill"] == "report":
            continue
        context = Context(
            pid,
            "reproduction",
            step["id"],
            manifest["snapshot"],
            step["parameters"],
            outputs,
            step.get("inputs", {}),
        )
        if step["skill"] == "custom_analysis":
            from yanji.adaptive import execute as execute_program

            program = dict(step["program"])
            previous = next((r for r in manifest["results"] if r.get("step_id") == step["id"]), {})
            source = next(
                (a for a in previous.get("artifacts", []) if a["artifact_type"] == "code"),
                None,
            )
            if source:
                program["code"] = (
                    root / "artifacts" / (source["id"] + "_" + source["filename"])
                ).read_text()
            result = execute_program(
                context, program, manifest["plan"]["objective"], review_results=False
            )
        else:
            result = execute(context, step["skill"])
        result["step_id"] = step["id"]
        outputs.append(result)
        print(step["skill"], result["status"], result["summary"])
    (Path(os.environ["YANJI_RUNTIME"]) / "results.json").write_text(
        json.dumps(outputs, ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    main()
