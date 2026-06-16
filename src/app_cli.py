# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import sys

from src.predict import extract_job_offer


def main() -> None:
    debug = "--debug" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if args and args[0] == "-":
        text = sys.stdin.read()
    elif args:
        try:
            with open(args[0], encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:
            print(f"Error: file not found '{args[0]}'", file=sys.stderr)
            sys.exit(1)
    else:
        print("Usage: python app_cli.py [--debug] <file>|-", file=sys.stderr)
        sys.exit(1)

    result = extract_job_offer(text, debug=debug)

    if debug and "segments_classes" in result:
        print("--- Segments classés (debug) ---")
        for seg in result["segments_classes"]:
            print(f"  [{seg['label']:>12}] {seg['text']}")
        print()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
