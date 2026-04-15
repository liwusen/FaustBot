import os
import runpy
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: embedded_python_bootstrap.py <script> [args...]")
        return 1

    script_path = os.path.abspath(sys.argv[1])
    script_dir = os.path.dirname(script_path)
    repo_root = os.path.dirname(os.path.abspath(__file__))

    extra_paths = [script_dir, repo_root, os.getcwd()]
    for path in reversed(extra_paths):
        if path and path not in sys.path:
            sys.path.insert(0, path)

    sys.argv = [script_path, *sys.argv[2:]]
    runpy.run_path(script_path, run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())