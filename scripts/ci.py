"""Cross-platform CI commands; no helper compilation or permission prompts."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]


def run(*command, cwd=ROOT):
    subprocess.run([str(part) for part in command], cwd=cwd, check=True)


def python_in(directory):
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def prepare(work):
    directory = work / "python"
    python = python_in(directory)
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(directory)
        run(python, "-m", "pip", "install", "--require-hashes", "-r", ROOT / "requirements-ci.txt")
        run(python, "-m", "pip", "install", "--no-deps", "--no-build-isolation", "-e", ROOT)
    return python


def protocol(python, executable, work, unsupported):
    run(python, ROOT / "tests/protocol.py", executable, str(unsupported), cwd=work)


def execute(mode, work):
    python = prepare(work)
    if mode == "unit":
        run(python, "-m", "unittest", "discover", "-s", "scripts/tests", "-q")
        run(python, "-m", "pytest", "tests/test_adapter.py", "--cov=cortex_vision", "--cov-report=term-missing", "--cov-report=xml", "--cov-fail-under=90")
    elif mode == "regression":
        run(python, "-m", "pytest", "tests/test_adapter.py", "-k", "failures or errors or routing or platform_rejection")
    elif mode == "e2e":
        executable = python.parent / ("cortex-vision.exe" if os.name == "nt" else "cortex-vision")
        protocol(python, executable, work, sys.platform != "darwin")
    elif mode == "environment":
        run(python, ROOT / "tests/protocol.py", python, str(sys.platform != "darwin"), ROOT, cwd=work)
    elif mode == "install":
        wheel_dir = work / "wheel"
        run(python, "-m", "build", "--wheel", "--no-isolation", "--outdir", wheel_dir)
        wheel, = wheel_dir.glob("*.whl")
        clean = work / "installed"
        venv.EnvBuilder(with_pip=True).create(clean)
        installed = python_in(clean)
        run(installed, "-m", "pip", "install", "--require-hashes", "-r", ROOT / "requirements-ci.txt")
        run(installed, "-m", "pip", "install", "--no-deps", wheel)
        run(installed, "-c", "import cortex_vision; from pathlib import Path; assert Path(cortex_vision.__file__).is_relative_to(Path(r'" + str(clean) + "'))", cwd=work)
        executable = installed.parent / ("cortex-vision.exe" if os.name == "nt" else "cortex-vision")
        protocol(installed, executable, work, sys.platform != "darwin")
    else:
        raise ValueError(f"unknown CI command: {mode}")


def main():
    mode = sys.argv[1]
    scratch = os.environ.get("CI_WORK")
    if scratch:
        execute(mode, Path(scratch))
    else:
        with tempfile.TemporaryDirectory(prefix="cortex-vision-ci-") as directory:
            execute(mode, Path(directory))


if __name__ == "__main__":
    main()
