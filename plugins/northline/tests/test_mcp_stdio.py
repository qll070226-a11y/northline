import asyncio
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class McpStdioTests(unittest.TestCase):
    def test_stdio_server_initializes_and_lists_tools(self):
        project = Path(__file__).parents[1]

        async def exercise():
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "northline.mcp_server"],
                cwd=project,
            )
            async with stdio_client(parameters) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    return {tool.name for tool in tools.tools}

        self.assertEqual(
            asyncio.run(exercise()),
            {
                "validate_handoff",
                "check_transition",
                "check_parallel_safety",
                "initialize_project",
                "draft_project_contract",
                "delegate_project_task",
                "prepare_project_workspace",
                "transition_project_handoff",
                "get_project_status",
                "get_project_resume",
                "draft_project_receipt",
                "verify_project_handoff",
                "record_project_integration",
                "submit_project_escalation",
                "decide_project_escalation",
                "revise_project_contract",
            },
        )

    def test_windows_launcher_performs_jsonrpc_handshake(self):
        project = Path(__file__).parents[1]
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "northline-test", "version": "1.0"},
            },
        }
        environment = os.environ.copy()
        environment["NORTHLINE_PYTHON"] = sys.executable
        completed = subprocess.run(
            ["cmd.exe", "/d", "/s", "/c", "call", "scripts\\launch_mcp.cmd"],
            cwd=project,
            env=environment,
            input=json.dumps(request) + "\n",
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        response = json.loads(completed.stdout.strip())
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["result"]["serverInfo"]["name"], "northline")


if __name__ == "__main__":
    unittest.main()
