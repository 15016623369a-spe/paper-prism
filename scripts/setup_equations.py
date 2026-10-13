#!/usr/bin/env python3
"""Install/check the isolated equation tool. No global or bundled-runtime writes."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

VERSION = "4.1.3"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool-dir", default=os.environ.get("LITERATURE_READER_MATH_DIR", str(Path.home() / ".cache/literature-reader/mathjax")))
    parser.add_argument("--node", default=shutil.which("node"))
    parser.add_argument("--npm", default=shutil.which("npm"))
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if not args.node:
        parser.error("Node.js unavailable: discover the host runtime first.")
    directory = Path(args.tool_dir).expanduser().resolve()
    package = directory / "node_modules/@mathjax/src/package.json"
    available = package.exists() and json.loads(package.read_text()).get("version") == VERSION
    if not available:
        if args.check_only:
            raise SystemExit("Equation tool missing; run setup without --check-only.")
        if not args.npm:
            parser.error("npm unavailable: discover a package manager before installing.")
        directory.mkdir(parents=True, exist_ok=True)
        manifest = {"name": "paper-prism-equations", "private": True,
                    "dependencies": {"@mathjax/src": VERSION}}
        (directory / "package.json").write_text(json.dumps(manifest, indent=2) + "\n")
        subprocess.run([args.npm, "install", "--prefix", str(directory), "--cache", str(directory / ".npm-cache"),
                        "--ignore-scripts", "--no-audit", "--no-fund"], check=True)
    probe = "const{createRequire}=require('node:module'); const r=createRequire(process.argv[1]+'/package.json'); r('@mathjax/src/js/mathjax.js');r('@mathjax/src/js/output/svg.js');console.log('MathJax modules load');"
    subprocess.run([args.node, "-e", probe, str(directory)], check=True)
    print(json.dumps({"ready": True, "version": VERSION, "tool_dir": str(directory), "reused": available}))

if __name__ == "__main__":
    main()
