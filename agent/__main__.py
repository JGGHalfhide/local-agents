"""Entry point of the agent image (python -m agent). Week 2 step 2 replaces
this with the status reporter; for now it proves the image runs and its
dependencies import."""
import sys

import openai

from agent import __version__


def main():
    print(f"local-agents {__version__}, openai {openai.__version__}, python {sys.version.split()[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
