"""Set up dependencies locally. Run --check to check without installing."""
from pathlib import Path
import importlib.util
import subprocess
import sys
import venv

def main():
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required. Install it from python.org, then try again.")
    if "--check" in sys.argv:
        missing = [n for n in ("lxml", "pypdf", "tzdata") if importlib.util.find_spec(n) is None]
        print("Python version: " + sys.version.split()[0])
        print("Dependencies: " + ("missing " + ", ".join(missing) if missing else "available"))
        raise SystemExit(1 if missing else 0)
    root = Path(__file__).resolve().parent
    environment = root / ".venv"
    print("Creating a Python environment inside this folder...", flush=True)
    venv.EnvBuilder(with_pip=True, clear=False).create(environment)
    executable = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    print("Installing the packages listed in requirements.txt...", flush=True)
    subprocess.run([str(executable), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(root / "requirements.txt")], check=True)
    print("Setup complete. On Windows, double-click Run morning note.cmd.")

if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as exc:
        print("Setup failed: " + str(exc), file=sys.stderr)
        print("Check your internet connection and any workplace package-installation restrictions.", file=sys.stderr)
        raise SystemExit(1)
