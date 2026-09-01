#!/usr/bin/env python3
"""Minimal MCP stdio client for driving mcp via its documented launcher.

The launcher script loads the dev JWT itself; this client never sees the token.
Used for Phase 0 discovery and later as the harness's reference/query path.
"""
import json
import os
import subprocess
import sys
import threading
import queue
import time

LAUNCHER = os.environ.get("SOD_MCP_LAUNCHER", "")  # path to your MCP stdio launcher


class McpStdioClient:
    def __init__(self, launcher=LAUNCHER, env_overrides=None, timeout=60):
        import os
        env = dict(os.environ)
        if env_overrides:
            env.update(env_overrides)
        self.proc = subprocess.Popen(
            [launcher], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, text=True, bufsize=1)
        self.timeout = timeout
        self._id = 0
        self._q = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._stderr_lines = []
        self._err_reader = threading.Thread(target=self._err_loop, daemon=True)
        self._err_reader.start()

    def _read_loop(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._q.put(json.loads(line))
            except json.JSONDecodeError:
                pass

    def _err_loop(self):
        for line in self.proc.stderr:
            self._stderr_lines.append(line.rstrip())

    def _rpc(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            self._id += 1
            msg["id"] = self._id
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        if notify:
            return None
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                resp = self._q.get(timeout=deadline - time.time())
            except queue.Empty:
                break
            if resp.get("id") == self._id:
                return resp
        raise TimeoutError(f"no response to {method}; stderr tail: "
                           f"{self._stderr_lines[-5:]}")

    def initialize(self):
        r = self._rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "sod-harness", "version": "0.1"}})
        self._rpc("notifications/initialized", {}, notify=True)
        return r

    def list_tools(self):
        return self._rpc("tools/list", {})

    def call_tool(self, name, arguments=None):
        return self._rpc("tools/call",
                         {"name": name, "arguments": arguments or {}})

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        self.proc.terminate()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    c = McpStdioClient()
    try:
        init = c.initialize()
        if cmd == "list":
            tools = c.list_tools()
            for t in tools["result"]["tools"]:
                print(t["name"], "-", (t.get("description") or "")[:100])
        elif cmd == "call":
            name = sys.argv[2]
            args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
            r = c.call_tool(name, args)
            print(json.dumps(r, indent=2)[:6000])
    finally:
        c.close()
