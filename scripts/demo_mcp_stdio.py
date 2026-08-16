"""Exercise the Nutcracker MCP server through a real stdio subprocess."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def run_demo() -> None:
    """Start the server, negotiate MCP, list tools, save, and recall."""

    with TemporaryDirectory(prefix="nutcracker-mcp-") as temporary:
        repo_root = Path(temporary)
        (repo_root / "auth.py").write_text("AUTH = True\n", encoding="utf-8")
        db_path = repo_root / ".nutcracker" / "memory.db"
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server.server"],
            cwd=PROJECT_ROOT,
            env={
                **os.environ,
                "NUTCRACKER_REPO_ROOT": str(repo_root),
                "NUTCRACKER_DB_PATH": str(db_path),
            },
        )

        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                saved = await session.call_tool(
                    "memory_save",
                    {
                        "summary": (
                            "Refresh token rotation is owned by the "
                            "authentication session layer."
                        ),
                        "anchors": [
                            {
                                "symbol": "auth.py",
                                "level": "structural",
                                "relation": "primary",
                            }
                        ],
                    },
                )
                recalled = await session.call_tool(
                    "memory_recall",
                    {"query": "authentication refresh token session"},
                )

        print(f"Tools: {', '.join(tool.name for tool in tools.tools)}")
        print(f"Save: {saved.structuredContent}")
        print(f"Recall: {recalled.structuredContent}")


if __name__ == "__main__":
    asyncio.run(run_demo())
