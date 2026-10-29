"""Check that an imported package belongs to the expected installed environment."""
import importlib
from pathlib import Path
import sys


def main():
    package = importlib.import_module(sys.argv[1])
    actual = Path(package.__file__).resolve()
    expected = Path(sys.argv[2]).resolve()
    if not actual.is_relative_to(expected):
        raise AssertionError(f"{actual} is outside expected installation {expected}")
    print(f"PASS installed import: {actual} inside {expected}")


if __name__ == "__main__":
    main()
