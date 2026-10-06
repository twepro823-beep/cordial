#!/usr/bin/env python3
"""Exercise ten fullscreen transitions through Cordial's own devctl socket.

This is intentionally compositor-neutral: run the current build normally with
CORDIAL_DEV_CONTROL=1, then run this script in another terminal. Every state is
accepted only when presents advance between two readings and a swapchain
screenshot succeeds. Artifacts stay outside the repository by default.
"""

import argparse
import json
import os
import re
import socket
import sys
import time


def default_socket(profile):
    data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(data, "cordial", "profiles", profile, "devctl.sock")


class Devctl:
    def __init__(self, path):
        self.path = path

    def send(self, command, timeout=20):
        with socket.socket(socket.AF_UNIX) as stream:
            stream.settimeout(timeout)
            stream.connect(self.path)
            stream.sendall((command + "\n").encode())
            reply = b""
            while not reply.endswith(b"\n"):
                part = stream.recv(65536)
                if not part:
                    break
                reply += part
        text = reply.decode(errors="replace").strip()
        if text.startswith("err "):
            raise RuntimeError(f"{command}: {text}")
        return text

    def info(self):
        text = self.send("info")
        presents = re.search(r"presents=(\d+)", text)
        extent = re.search(r"extent=(\d+)x(\d+)", text)
        if not presents or not extent:
            raise RuntimeError(f"unrecognised info reply: {text}")
        return {
            "presents": int(presents.group(1)),
            "extent": [int(extent.group(1)), int(extent.group(2))],
            "raw": text,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="default")
    parser.add_argument("--socket", help="devctl socket; overrides --profile")
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--settle", type=float, default=1.5,
                        help="seconds between the two present readings")
    parser.add_argument("--out", default="/tmp/cordial-fullscreen-e2e")
    args = parser.parse_args()
    if args.cycles < 1:
        parser.error("--cycles must be at least 1")
    dev = Devctl(args.socket or default_socket(args.profile))
    os.makedirs(args.out, exist_ok=True)
    results = []

    for cycle in range(1, args.cycles + 1):
        for enabled, command in ((True, "fullscreen"), (False, "windowed")):
            dev.send(command)
            time.sleep(0.5)
            first = dev.info()
            time.sleep(args.settle)
            second = dev.info()
            shot = os.path.join(
                args.out, f"{cycle:02d}-{'fullscreen' if enabled else 'windowed'}.png"
            )
            dev.send(f"screenshot {shot}")
            ok = (
                second["presents"] > first["presents"]
                and second["extent"][0] > 0
                and second["extent"][1] > 0
                and os.path.isfile(shot)
                and os.path.getsize(shot) > 0
            )
            row = {
                "cycle": cycle,
                "fullscreen": enabled,
                "first": first,
                "second": second,
                "screenshot": shot,
                "ok": ok,
            }
            results.append(row)
            print(
                f"{'PASS' if ok else 'FAIL'} cycle={cycle} state={command} "
                f"presents={first['presents']}->{second['presents']} "
                f"extent={second['extent'][0]}x{second['extent'][1]} shot={shot}",
                flush=True,
            )

    report = os.path.join(args.out, "report.json")
    with open(report, "w", encoding="utf-8") as output:
        json.dump(results, output, indent=2)
        output.write("\n")
    failed = [row for row in results if not row["ok"]]
    print(f"report={report} states={len(results)} failed={len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
