"""Record one real request against an existing swarm session; never start a session or simulate output."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from swarm.config import load_settings


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--wait-seconds", type=float, default=660)
    args = parser.parse_args()
    settings = load_settings()
    folder = settings.state_path / "test-runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, mode=0o700)
    base = f"http://127.0.0.1:{settings.api_port}"
    headers = {"Authorization": "Bearer " + settings.token}
    result = {"started_at": now(), "request_submitted": False, "complete": False, "usage": None}
    output = ""
    session = None
    started = time.monotonic()

    def save(name, value):
        (folder / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")

    print("Recording directory:", folder, flush=True)
    with httpx.Client(trust_env=False, headers=headers, timeout=10) as client:
        def snapshot():
            response = client.get(base + "/api/state")
            response.raise_for_status()
            state = response.json()
            with (folder / "peer-observations.jsonl").open("a") as file:
                file.write(json.dumps({"at": now(), "state": state}) + "\n")
            return state

        try:
            state = snapshot()
            session = state["local"]["session"]
            if not session:
                raise RuntimeError("No session is active; this recorder does not start one")
            save("session.json", session)
            prompt = args.prompt_file.read_text() if args.prompt_file else state["sample_prompt"]
            request = {"prompt": prompt, "max_tokens": 256}
            save("input.json", {"recorded_at": now(), "request": request,
                 "native_sampling_from_app_code": {"temperature": 0, "seed": 42},
                 "model_sha256": session["model_sha256"]})
            (folder / "input.txt").write_text(prompt)
            deadline = time.monotonic() + args.wait_seconds
            last_status, last_print = None, 0.0
            while True:
                if state["local"]["session"] != session:
                    raise RuntimeError("The session changed before generation")
                coordinator = next(p for p in state["peers"] if p["id"] == session["coordinator"])
                if coordinator["state"] == "failed":
                    raise RuntimeError(coordinator.get("error") or "Coordinator failed")
                if coordinator["state"] == "ready":
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("Timed out waiting for the existing model session")
                if coordinator["state"] != last_status or time.monotonic() - last_print >= 30:
                    print("Waiting for model:", coordinator["state"], flush=True)
                    last_status, last_print = coordinator["state"], time.monotonic()
                time.sleep(5)
                state = snapshot()
            save("before-request.json", state)
            result["observed_readiness_wait_seconds"] = round(time.monotonic() - started, 3)
            result["request_submitted"] = True
            result["submitted_at"] = now()
            submitted = time.monotonic()
            with (folder / "stream.jsonl").open("a") as stream_log, (folder / "output.txt").open("w") as output_log:
                with client.stream("POST", base + f"/api/sessions/{session['id']}/generate",
                                   json=request, timeout=httpx.Timeout(190, connect=10)) as response:
                    if response.is_error:
                        result["http_status"] = response.status_code
                        raise RuntimeError(response.read().decode(errors="replace")[:1000])
                    for line in response.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        event = json.loads(line[6:])
                        stream_log.write(json.dumps({"at": now(), "event": event}) + "\n")
                        stream_log.flush()
                        if event["type"] == "token":
                            output += event["text"]
                            output_log.write(event["text"])
                            output_log.flush()
                            print(event["text"], end="", flush=True)
                        elif event["type"] == "error":
                            raise RuntimeError(event["message"])
                        elif event["type"] == "done":
                            result.update(event)
                if not result["complete"]:
                    raise RuntimeError("Stream ended without a successful completion event")
            result["client_request_seconds"] = round(time.monotonic() - submitted, 3)
        except (Exception, KeyboardInterrupt) as exc:
            result["complete"] = False
            result["error"] = str(exc) or type(exc).__name__
            print("\nIncomplete test:", result["error"], flush=True)
        finally:
            result["finished_at"] = now()
            result["output"] = output
            (folder / "output.txt").write_text(output)
            result["usage_available"] = result.get("usage") is not None
            result["memory_note"] = "Peer RSS observations include loading and generation; they do not fully measure GPU/unified memory or establish a hard memory cap."
            save("result.json", result)
            save("usage.json", {"available": result["usage_available"], "usage": result.get("usage")})
            try:
                save("after-request.json", snapshot())
            except Exception as exc:
                save("observation-error.json", {"error": str(exc)})
            if session:
                native_log = settings.state_path / f"{session['id']}-coordinator.log"
                if native_log.is_file():
                    shutil.copyfile(native_log, folder / "coordinator-native.log")
            print("\nSaved evidence:", folder, flush=True)
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
