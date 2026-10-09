"""Check TrustCheck's Python dependencies and the Tesseract executable."""

from __future__ import annotations

import importlib
import shutil
import sys


# (distribution name, module names to try, exact repair command)
PACKAGE_CHECKS = (
    ("fastapi", ("fastapi",), "pip install fastapi"),
    ("uvicorn[standard]", ("uvicorn",), 'pip install "uvicorn[standard]"'),
    ("python-multipart", ("python_multipart", "multipart"), "pip install python-multipart"),
    ("pillow", ("PIL",), "pip install pillow"),
    ("opencv-python-headless", ("cv2",), "pip install opencv-python-headless"),
    ("pytesseract", ("pytesseract",), "pip install pytesseract"),
    ("exifread", ("exifread",), "pip install exifread"),
    ("qrcode[pil]", ("qrcode",), 'pip install "qrcode[pil]"'),
    ("passlib[bcrypt]", ("passlib",), 'pip install "passlib[bcrypt]"'),
    ("bcrypt==4.0.1", ("bcrypt",), "pip install bcrypt==4.0.1"),
    (
        "python-jose[cryptography]",
        ("jose",),
        'pip install "python-jose[cryptography]"',
    ),
)


def import_one_of(module_names: tuple[str, ...]) -> tuple[bool, str]:
    """Return whether one of the listed import names can be imported."""
    for module_name in module_names:
        try:
            importlib.import_module(module_name)
            return True, module_name
        except Exception:
            # Some native packages raise errors other than ImportError when
            # their installation is incomplete, so report those as missing too.
            continue
    return False, module_names[0]


def main() -> int:
    print("TrustCheck setup check")
    print(f"Python {sys.version.split()[0]} ({sys.executable})")

    python_ok = sys.version_info >= (3, 11)
    if python_ok:
        print(f"OK Python {sys.version.split()[0]}")
    else:
        print(f"MISSING Python 3.11+ (found {sys.version.split()[0]})")
        print("    Install Python 3.11 or newer from https://www.python.org/downloads/")
        print("    Windows: tick 'Add Python to PATH' in the installer.")

    if sys.prefix != sys.base_prefix:
        print("OK virtual environment is active")
    else:
        print("NOTE virtual environment is not active")
        print(r"    Windows: venv\Scripts\activate")
        print("    Mac:     source venv/bin/activate")

    missing: list[tuple[str, str]] = []
    print("\nPython packages:")
    for distribution, module_names, fix_command in PACKAGE_CHECKS:
        installed, imported_name = import_one_of(module_names)
        if installed and distribution == "bcrypt==4.0.1":
            bcrypt = importlib.import_module("bcrypt")
            installed_version = getattr(bcrypt, "__version__", "unknown")
            installed = installed_version == "4.0.1"

        if installed:
            if distribution == "bcrypt==4.0.1":
                print(f"OK {distribution} (import {imported_name})")
            else:
                print(f"OK {distribution} (import {imported_name})")
        else:
            missing.append((distribution, fix_command))
            print(f"MISSING {distribution}")
            print(f"    Fix: {fix_command}")

    print("\nTesseract OCR engine:")
    tesseract_path = shutil.which("tesseract")
    if tesseract_path:
        print(f"OK Tesseract found at {tesseract_path}")
    else:
        print("MISSING Tesseract executable")
        print("    Backend B installs Tesseract; ask Backend B if it is not found.")

    if missing or not python_ok:
        print("\nSetup is not ready. Install the missing items above and rerun this script.")
        return 1

    print("\nAll required Python packages are available.")
    if not tesseract_path:
        print("Ask Backend B about Tesseract before testing OCR features.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
