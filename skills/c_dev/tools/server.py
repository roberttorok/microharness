from mcp.server.mcpserver import MCPServer
import os
import subprocess
import tempfile

mcp = MCPServer("c_dev")

CFLAGS = ["-Wall", "-Wextra", "-std=c11"]


def run(args: list[str], timeout: int = 15) -> str:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout
        )
        return (result.stdout + result.stderr).strip() or "(no output)"
    except FileNotFoundError:
        return f"Error: {args[0]} is not installed"
    except subprocess.TimeoutExpired:
        return f"Error: timed out after {timeout} seconds"


@mcp.tool()
def c_compile(path: str) -> str:
    """
        Compiles a C file with warnings enabled, without running it.
    """
    output = run(["gcc", *CFLAGS, "-fsyntax-only", path])
    return "No errors or warnings." if output == "(no output)" else output


@mcp.tool()
def c_run(path: str) -> str:
    """
        Compiles a C file and runs it, returning its output.
    """
    with tempfile.TemporaryDirectory() as tmp:
        binary = os.path.join(tmp, "a.out")
        build = run(["gcc", *CFLAGS, "-o", binary, path])
        if not os.path.exists(binary):
            return f"Compilation failed:\n{build}"
        return run([binary], timeout=10)


if __name__ == "__main__":
    mcp.run(transport="stdio")
