# -*- coding: utf-8 -*-
"""
LM-Chat™ Autonomous Standalone Versioning & Release Tool.
Provides local SemVer 2.0.0 automated version bumping, sanity checks,
multi-file synchronization, and changelog management with zero external dependencies.
"""

import sys
import os
import re
import argparse
import datetime
import subprocess
from typing import Tuple, Dict, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Versioned target files and their regex patterns
VERSIONED_TARGETS = {
    "extension_toml": {
        "path": os.path.join(REPO_ROOT, "config", "extension.toml"),
        "pattern": r'(^version\s*=\s*")([^"]+)(")',
        "replace": r'\g<1>{new_version}\g<3>',
    },
    "pyproject": {
        "path": os.path.join(REPO_ROOT, "pyproject.toml"),
        "pattern": r'(^version\s*=\s*")([^"]+)(")',
        "replace": r'\g<1>{new_version}\g<3>',
    },
    "init_py": {
        "path": os.path.join(REPO_ROOT, "__init__.py"),
        "pattern": r'(^__version__\s*=\s*")([^"]+)(")',
        "replace": r'\g<1>{new_version}\g<3>',
    },
    "citation_cff": {
        "path": os.path.join(REPO_ROOT, "CITATION.cff"),
        "pattern": r'(^version:\s*)([^\r\n]+)',
        "replace": r'\g<1>{new_version}',
    }
}


def read_file(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def write_file(filepath: str, content: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def check_version_sanity() -> str:
    """Verifies that all targets currently share the exact same version string."""
    versions: Dict[str, str] = {}
    for name, target in VERSIONED_TARGETS.items():
        if not os.path.exists(target["path"]):
            continue
        content = read_file(target["path"])
        match = re.search(target["pattern"], content, re.MULTILINE)
        if match:
            versions[name] = match.group(2).strip()
        else:
            raise ValueError(f"No se pudo extraer la versión de: {target['path']}")

    unique_versions = set(versions.values())
    if len(unique_versions) > 1:
        raise RuntimeError(
            f"[Sanity Check Falló] Versiones asíncronas detectadas en el repositorio: {versions}. "
            "Por favor, sincroniza los archivos antes de continuar."
        )

    return list(unique_versions)[0]


def parse_semver(version_str: str) -> Tuple[int, int, int]:
    clean = version_str.lstrip("v").strip()
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", clean)
    if not match:
        raise ValueError(f"Formato SemVer inválido: '{version_str}'. Debe ser X.Y.Z")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def calculate_bump(current_version: str, bump_type: str) -> str:
    major, minor, patch = parse_semver(current_version)
    b_type = bump_type.lower()
    if b_type == "patch":
        patch += 1
    elif b_type == "minor":
        minor += 1
        patch = 0
    elif b_type == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        raise ValueError(f"Tipo de incremento inválido: '{bump_type}'. Opciones: patch, minor, major")

    return f"{major}.{minor}.{patch}"


def update_target_files(new_version: str, dry_run: bool = False) -> None:
    today_str = datetime.date.today().isoformat()
    for name, target in VERSIONED_TARGETS.items():
        filepath = target["path"]
        if not os.path.exists(filepath):
            continue
        content = read_file(filepath)
        updated = re.sub(
            target["pattern"],
            target["replace"].format(new_version=new_version),
            content,
            flags=re.MULTILINE
        )

        # Update date in citation.cff if applicable
        if name == "citation_cff":
            updated = re.sub(
                r'(^date-released:\s*)([^\r\n]+)',
                rf'\g<1>{today_str}',
                updated,
                flags=re.MULTILINE
            )

        if dry_run:
            print(f"[Dry Run] Actualizaría: {os.path.relpath(filepath, REPO_ROOT)}")
        else:
            write_file(filepath, updated)
            print(f"[✓] Actualizado: {os.path.relpath(filepath, REPO_ROOT)} -> v{new_version}")


def update_changelog(new_version: str, dry_run: bool = False) -> None:
    changelog_path = os.path.join(REPO_ROOT, "docs", "CHANGELOG.md")
    if not os.path.exists(changelog_path):
        return

    today_str = datetime.date.today().isoformat()
    content = read_file(changelog_path)

    new_section = (
        f"## [{new_version}] - {today_str}\n\n"
        f"### Cambios\n"
        f"- Nueva versión comercial v{new_version} sincronizada automáticamente para NVIDIA Omniverse Kit.\n\n"
    )

    # Insert below the introductory header
    marker = "---\n\n"
    if marker in content:
        parts = content.split(marker, 1)
        updated_content = parts[0] + marker + new_section + parts[1]
    else:
        updated_content = content + "\n\n" + new_section

    if dry_run:
        print(f"[Dry Run] Añadiría sección v{new_version} a docs/CHANGELOG.md")
    else:
        write_file(changelog_path, updated_content)
        print(f"[✓] docs/CHANGELOG.md actualizado con sección v{new_version}")


def run_git_operations(new_version: str) -> None:
    tag_name = f"v{new_version}"
    commit_msg = f"bump: version {new_version}"

    files_to_stage = [
        "config/extension.toml",
        "pyproject.toml",
        "__init__.py",
        "CITATION.cff",
        "docs/CHANGELOG.md"
    ]

    subprocess.run(["git", "add"] + files_to_stage, cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"], cwd=REPO_ROOT, check=True)

    print(f"\n[Éxito] Commit y Tag Git creados localmente: {tag_name}")
    print("Para publicar el lanzamiento oficial a GitHub ejecuta:")
    print(f"  git push origin main && git push origin {tag_name}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LM-Chat™ Automated Standalone Versioning Tool (SemVer 2.0.0)"
    )
    parser.add_argument(
        "bump",
        nargs="?",
        choices=["patch", "minor", "major"],
        default=None,
        help="Tipo de incremento de versión (patch: 1.0.1, minor: 1.1.0, major: 2.0.0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula el incremento sin modificar archivos ni crear commits en git",
    )

    args = parser.parse_args()

    print("=" * 65)
    print("  LM-Chat™ Automated Versioning & Release Manager")
    print("=" * 65)

    try:
        current_version = check_version_sanity()
        print(f"[Sanity Check]: Versión actual sincronizada: v{current_version}")
    except Exception as e:
        print(f"[Error de Verificación]: {e}")
        sys.exit(1)

    bump_type = args.bump
    if not bump_type:
        print("\nSelecciona el tipo de versión a generar:")
        print("  1) patch (1.0.0 -> 1.0.1 - corrección de errores)")
        print("  2) minor (1.0.0 -> 1.1.0 - nueva funcionalidad retrocompatible)")
        print("  3) major (1.0.0 -> 2.0.0 - cambio mayor incompatible)")
        choice = input("Opción [1-3] (default: 1): ").strip()
        mapping = {"1": "patch", "2": "minor", "3": "major", "": "patch"}
        bump_type = mapping.get(choice, "patch")

    new_version = calculate_bump(current_version, bump_type)
    print(f"\nIncrementando versión: v{current_version} -> v{new_version} ({bump_type.upper()})\n")

    update_target_files(new_version, dry_run=args.dry_run)
    update_changelog(new_version, dry_run=args.dry_run)

    if not args.dry_run:
        try:
            run_git_operations(new_version)
        except Exception as e:
            print(f"[Aviso Git]: No se pudo realizar el commit automático: {e}")
            print("Puedes confirmar los cambios manualmente con 'git add .' y 'git commit'.")
    else:
        print("\n[Dry Run Completado]: Ningún archivo fue modificado.")


if __name__ == "__main__":
    main()
