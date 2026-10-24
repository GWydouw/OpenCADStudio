#!/usr/bin/env python3
"""Validate fork beta versions and verify every download before publication."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib


def versions(tag):
    match = re.fullmatch(r"v(20\d{2})\.(\d{1,2})\.([1-9]\d*)-beta\.([1-9]\d*)", tag)
    if not match:
        raise ValueError(f"Invalid beta tag: {tag}")
    year, week, patch, beta = map(int, match.groups())
    from datetime import date
    date.fromisocalendar(year, week, 1)
    if patch > 65535:
        raise ValueError("Beta patch exceeds the MSI version limit")
    cargo = f"{year}.{week}.{patch}-beta.{beta}"
    if tag != f"v{cargo}":
        raise ValueError("Beta tag must use the canonical Cargo version")
    manifest = tomllib.loads(Path("Cargo.toml").read_text())
    if manifest["package"]["version"] != cargo:
        raise ValueError("Beta tag and Cargo version do not match")
    lock = tomllib.loads(Path("Cargo.lock").read_text())
    locked = [p["version"] for p in lock["package"] if p["name"] == "OpenCADStudio"]
    if locked != [cargo]:
        raise ValueError("Cargo.lock does not match the beta version")
    return {"version": cargo, "cargo": f"{year}.{week}.{patch}", "msi": f"{year - 2000}.{week}.{patch}"}


def verify(tag, repo):
    versions(tag)
    release = json.loads(subprocess.check_output([
        "gh", "release", "view", tag, "--repo", repo,
        "--json", "assets,body,isPrerelease,targetCommitish",
    ], text=True))
    suffixes = ("windows-x86_64-portable.exe", "windows-x86_64-installer.msi", "macos-arm64.dmg")
    expected = {f"OpenCADStudio-{tag}-{suffix}" for suffix in suffixes}
    sums = {f"OpenCADStudio-{tag}-{platform}-SHA256SUMS.txt" for platform in ("windows", "macos")}
    uploaded = {a["name"] for a in release["assets"] if a["size"] > 0 and a["state"] == "uploaded"}
    if not expected.union(sums) <= uploaded or not release["body"].strip() or not release["isPrerelease"]:
        raise ValueError("Beta metadata or downloads are incomplete")
    with tempfile.TemporaryDirectory() as directory:
        args = ["gh", "release", "download", tag, "--repo", repo, "--dir", directory]
        for name in sorted(expected | sums):
            args += ["--pattern", name]
        subprocess.run(args, check=True)
        recorded = {}
        for name in sorted(sums):
            for line in (Path(directory) / name).read_text().splitlines():
                digest, filename = line.strip().split("  ", 1)
                if filename not in expected or filename in recorded or not re.fullmatch(r"[a-f0-9]{64}", digest):
                    raise ValueError("Invalid checksum manifest")
                recorded[filename] = digest
        if recorded.keys() != expected:
            raise ValueError("Missing download checksums")
        for name, digest in recorded.items():
            with (Path(directory) / name).open("rb") as source:
                actual = hashlib.file_digest(source, "sha256").hexdigest()
            if actual != digest:
                raise ValueError(f"Checksum mismatch: {name}")
            print(f"Verified SHA-256: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("versions", "verify"))
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repo")
    args = parser.parse_args()
    if args.command == "verify":
        if not args.repo:
            parser.error("verify requires --repo")
        verify(args.tag, args.repo)
    else:
        output = "".join(f"{key}={value}\n" for key, value in versions(args.tag).items())
        print(output, end="")
        if path := os.environ.get("GITHUB_OUTPUT"):
            with open(path, "a") as stream:
                stream.write(output)


if __name__ == "__main__":
    main()
