#!/usr/bin/env python3
"""Drive repeatable touch sequences through the Cordial MCP tool.

Run the client with CORDIAL_DEV_CONTROL=1 and CORDIAL_TRACE_TOUCH=1. Restart it
for each native-path arm described in docs/analysis/known-broken-validation.md;
this runner deliberately does not change process environment after launch.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_socket(profile):
    data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(data, "cordial", "profiles", profile, "devctl.sock")


class Mcp:
    def __init__(self, socket_path):
        self.next_id = 1
        self.proc = subprocess.Popen(
            [os.path.join(ROOT, "tools", "cordial-mcp.py"), "--socket", socket_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.request("initialize", {})

    def request(self, method, params):
        request_id = self.next_id
        self.next_id += 1
        self.proc.stdin.write(json.dumps({
            "jsonrpc": "2.0", "id": request_id, "method": method, "params": params,
        }) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError(f"MCP exited: {self.proc.stderr.read()}")
        reply = json.loads(line)
        result = reply.get("result", {})
        if result.get("isError"):
            raise RuntimeError(result.get("content"))
        return result

    def tool(self, name, arguments=None):
        return self.request("tools/call", {
            "name": name, "arguments": arguments or {},
        })

    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=5)


def content_text(result):
    return "\n".join(item.get("text", "") for item in result.get("content", []))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="default")
    parser.add_argument("--socket", help="devctl socket; overrides --profile")
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be at least 1")
    mcp = Mcp(args.socket or default_socket(args.profile))
    try:
        before = content_text(mcp.tool("cordial_info"))
        for repetition in range(1, args.repetitions + 1):
            calls = [
                ("begin", 7, 300, 220),
                ("update", 7, 340, 240),
                ("begin", 11, 600, 220),
                ("update", 11, 620, 250),
                ("end", 7, None, None),
                ("cancel", None, None, None),
            ]
            for action, contact, x, y in calls:
                arguments = {"action": action}
                if contact is not None:
                    arguments["id"] = contact
                if x is not None:
                    arguments.update(x=x, y=y)
                mcp.tool("cordial_touch", arguments)
            after = content_text(mcp.tool("cordial_info"))
            print(f"QUEUED repetition={repetition} client={after}", flush=True)

        applied_before = re.search(r"touch_phases=(\d+)", before)
        applied_after = None
        deadline = time.time() + 5
        while time.time() < deadline:
            after = content_text(mcp.tool("cordial_info"))
            applied_after = re.search(r"touch_phases=(\d+)", after)
            if applied_before and applied_after and (
                int(applied_after.group(1)) - int(applied_before.group(1))
                >= args.repetitions * 6
            ):
                break
            time.sleep(0.1)
        if not applied_before or not applied_after:
            raise RuntimeError(f"info did not expose touch_phases: {before!r} / {after!r}")
        expected = args.repetitions * 6
        observed = int(applied_after.group(1)) - int(applied_before.group(1))
        if observed < expected:
            raise RuntimeError(f"only {observed} of at least {expected} queued phases were applied")
        print(f"PASS applied={observed} expected-at-least={expected}")
        print("Inspect CORDIAL_TRACE_TOUCH for the last pre-call line; survival alone does not name the safe native path.")
        return 0
    finally:
        mcp.close()


if __name__ == "__main__":
    sys.exit(main())
