"""Build a plugin ZIP without dependencies: python scripts/package-plugin.py plugin/examples/sandbox-delegate output.zip"""
import argparse
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser(description="Package a trusted API v1 judging plugin")
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    files = [args.directory / name for name in ("plugin.json", "plugin.py")]
    if not all(path.is_file() for path in files):
        parser.error("directory must contain plugin.json and plugin.py")
    readme = args.directory / "README.md"
    if readme.is_file():
        files.append(readme)
    if sum(path.stat().st_size for path in files) > 262144:
        parser.error("uncompressed package must be <=256 KiB")
    with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.name)
    print(args.output)


if __name__ == "__main__":
    main()
