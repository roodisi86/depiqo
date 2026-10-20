"""Checks, after `expo prebuild`, that the release build type in android/app/build.gradle is signed.

    python3 .github/scripts/check_release_signing.py mobile/android/app/build.gradle

An unsigned release APK cannot be installed on the emulator or a phone. Expo's template signs release with the
debug keystore (fine for CI and sideloading; the stores need EAS credentials). This reads the generated file
instead of assuming the template, and exits 1 with the release block printed when it is not signed.
"""
import re
import sys


def block_after(src, start):
    """Text between the brace that follows `start` and its matching closing brace."""
    open_at = src.index("{", start)
    depth = 0
    for i in range(open_at, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[open_at + 1:i]
    raise ValueError("unbalanced braces")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "android/app/build.gradle"
    src = re.sub(r"//[^\n]*", "", open(path, encoding="utf-8").read())  # drop line comments
    m = re.search(r"\bbuildTypes\s*\{", src)
    if not m:
        sys.exit(f"{path}: no buildTypes block")
    build_types = block_after(src, m.start())
    r = re.search(r"\brelease\s*\{", build_types)
    if not r:
        sys.exit(f"{path}: no release build type")
    release = block_after(build_types, r.start())
    sign = re.search(r"signingConfig\s*(=\s*)?signingConfigs\.(\w+)", release)
    if not sign:
        print(release)
        sys.exit(f"{path}: the release build type has no signingConfig; the APK would be unsigned")
    print(f"release build type signed with signingConfigs.{sign.group(2)}")


if __name__ == "__main__":
    main()
