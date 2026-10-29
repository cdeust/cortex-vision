"""Real stdio MCP handshake against the installed console entrypoint.

macOS verifies startup and schemas only: never request capture/TCC in CI.
Other platforms additionally verify the documented unsupported-platform result.
"""
import asyncio
import json
import os
from pathlib import Path
import sys

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


async def main():
    args = []
    env = None
    if len(sys.argv) > 3:
        root = Path(sys.argv[3])
        manifest = json.loads((root / ".claude-plugin/plugin.json").read_text())
        config = manifest["mcpServers"]["cortex-vision"]
        assert config["command"] == "python3"
        args = [item.replace("${CLAUDE_PLUGIN_ROOT}", str(root)) for item in config["args"]]
        env = {"CLAUDE_PLUGIN_ROOT": str(root), "CLAUDE_PLUGIN_DATA": str(Path.cwd() / "plugin-data")}
        for key, template in config["env"].items():
            setting = template.removeprefix("${user_config.").removesuffix("}")
            env[key] = manifest["userConfig"][setting]["default"]
    async with Client(StdioTransport(command=sys.argv[1], args=args, env=env)) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert set(tools) == {"look", "check_vision_setup"}, tools
        assert "mode" in tools["look"].input_schema["properties"]
        if sys.argv[2] == "True":
            result = (await client.call_tool("check_vision_setup", {})).data
            assert result["ok"] is False, result
            assert "requires macOS" in result["error"], result
    print("PASS packaged cortex-vision entrypoint: stdio initialization, tools/list, schemas, platform contract")


if __name__ == "__main__":
    asyncio.run(main())
