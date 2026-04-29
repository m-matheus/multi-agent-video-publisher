import json
from pathlib import Path
from datetime import datetime, timezone


class StateManager:
    def __init__(self, state_path: Path = None):
        from .config import PROJECT_ROOT
        self.state_path = state_path or (PROJECT_ROOT / "state.json")
        self._ensure_state_file()

    def _ensure_state_file(self):
        if not self.state_path.exists():
            self._write({"current_run": None, "runs": [], "schema_version": "1.0.0"})

    def _read(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write(self, state: dict):
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def initialize_run(self, topic: str, content_type: str, output_dir: str) -> dict:
        state = self._read()
        run = {
            "run_id": Path(output_dir).name,
            "topic": topic,
            "content_type": content_type,
            "output_dir": output_dir,
            "started_at": self._now(),
            "completed_at": None,
            "status": "running",
            "steps": {},
        }
        state["current_run"] = run["run_id"]
        state["runs"].append(run)
        self._write(state)
        return run

    def _get_current_run(self, state: dict) -> dict:
        for run in state["runs"]:
            if run["run_id"] == state["current_run"]:
                return run
        raise ValueError("No active run found")

    def update_step(self, step_id: str, status: str, outputs: dict = None):
        state = self._read()
        run = self._get_current_run(state)
        if step_id not in run["steps"]:
            run["steps"][step_id] = {"started_at": self._now()}
        run["steps"][step_id]["status"] = status
        if status == "completed":
            run["steps"][step_id]["completed_at"] = self._now()
        if outputs:
            run["steps"][step_id]["outputs"] = outputs
        self._write(state)

    def mark_checkpoint(self, step_id: str, message: str):
        self.update_step(step_id, "awaiting_approval")
        state = self._read()
        run = self._get_current_run(state)
        run["steps"][step_id]["checkpoint_message"] = message
        self._write(state)

    def approve_checkpoint(self, step_id: str):
        state = self._read()
        run = self._get_current_run(state)
        run["steps"][step_id]["status"] = "approved"
        run["steps"][step_id]["approved_at"] = self._now()
        self._write(state)

    def complete_run(self):
        state = self._read()
        run = self._get_current_run(state)
        run["status"] = "completed"
        run["completed_at"] = self._now()
        state["current_run"] = None
        self._write(state)

    def get_state(self) -> dict:
        return self._read()
