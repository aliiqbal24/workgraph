"""Optional test against the real Python MCP client SDK; no model calls."""

import asyncio
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from workgraph.example import Example
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run():
    with tempfile.TemporaryDirectory(prefix="workgraph-mcp-") as directory:
        example = Example.create(Path(directory) / "repository")
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "workgraph", "--repo", str(example.engine.repo), "mcp", "--session", "sdk-test"],
            env={"PYTHONPATH": str(ROOT)})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert any(tool.name == "workgraph" for tool in tools.tools)
                opened = await session.call_tool("workgraph", {"action": "open", "intent": "MCP interoperability"})
                work = json.loads(opened.content[0].text)
                (Path(work["workspace"]) / "sdk.txt").write_text("actual MCP client\n")
                args = {"action": "checkpoint", "summary": "Saved through the MCP SDK", "request_id": "sdk-once"}
                first = json.loads((await session.call_tool("workgraph", args)).content[0].text)
                again = json.loads((await session.call_tool("workgraph", args)).content[0].text)
                assert first["revision"] == again["revision"]
                denied = json.loads((await session.call_tool("workgraph", {"action": "land"})).content[0].text)
                assert denied["error"] == "INVALID_ACTION"
                return {"passed": True, "client": "Python MCP SDK", "operations": ["initialize", "tools/list", "open", "checkpoint", "idempotent replay", "operator boundary"]}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), indent=2))
