# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Tests for NVIDIA Omniverse Kit Layout & Community Registry compliance.
Validates directory structure, extension.toml metadata, namespace invariants,
and visual asset integrity.
"""

import os
import re
import struct
import unittest
import importlib
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXT_DIR = os.path.join(REPO_ROOT, "exts", "orlandodorival.lm_chat")


class TestOmniverseExtensionLayout(unittest.TestCase):
    """Verifica el cumplimiento de las especificaciones de NVIDIA Omniverse Kit y Community Registry."""

    def test_directory_layout_structure(self):
        """Verifica que la extensión resida en exts/orlandodorival.lm_chat con sus componentes obligatorios."""
        self.assertTrue(os.path.isdir(EXT_DIR), f"El directorio {EXT_DIR} no existe.")

        expected_dirs = ["config", "ui", "logic", "mcp", "core", "data", "orlandodorival"]
        for d in expected_dirs:
            p = os.path.join(EXT_DIR, d)
            self.assertTrue(os.path.isdir(p), f"Falta el subdirectorio requerido: {p}")

        expected_files = [
            os.path.join(EXT_DIR, "extension.py"),
            os.path.join(EXT_DIR, "__init__.py"),
            os.path.join(EXT_DIR, "config", "extension.toml"),
            os.path.join(EXT_DIR, "data", "icon.png"),
            os.path.join(EXT_DIR, "data", "preview.png"),
            os.path.join(EXT_DIR, "orlandodorival", "__init__.py"),
            os.path.join(EXT_DIR, "orlandodorival", "lm_chat", "__init__.py"),
        ]
        for f in expected_files:
            self.assertTrue(os.path.isfile(f), f"Falta el archivo requerido: {f}")

    def test_extension_toml_mandatory_metadata(self):
        """Valida que extension.toml contenga todos los metadatos exigidos por el Extension Manager."""
        toml_path = os.path.join(EXT_DIR, "config", "extension.toml")
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        self.assertIn("package", data)
        pkg = data["package"]

        self.assertEqual(pkg.get("title"), "LM-Chat: AI Agent & MCP Integration")
        self.assertEqual(
            pkg.get("description"),
            "Autonomous Spatial AI Copilot for NVIDIA Omniverse with MCP, reasoning models, and cluster support."
        )
        self.assertEqual(pkg.get("repository"), "https://github.com/Orlandho/LM-Chat")
        self.assertEqual(pkg.get("changelog"), "docs/CHANGELOG.md")
        self.assertEqual(pkg.get("readme"), "README.md")
        self.assertEqual(pkg.get("preview_image"), "data/preview.png")
        self.assertEqual(pkg.get("icon"), "data/icon.png")
        self.assertTrue(re.match(r"^\d+\.\d+\.\d+", pkg.get("version", "")), f"Versión inválida en toml: {pkg.get('version')}")

        expected_keywords = ["ai", "llm", "mcp", "chat", "usd", "omniverse", "agent"]
        self.assertEqual(pkg.get("keywords"), expected_keywords)

        # Namespace invariant: Debe ser orlandodorival.lm_chat, nunca omni.*
        self.assertIn("python", data)
        self.assertIn("module", data["python"])
        modules = data["python"]["module"]
        self.assertTrue(len(modules) > 0)
        mod_name = modules[0].get("name")
        self.assertEqual(mod_name, "orlandodorival.lm_chat")
        self.assertFalse(mod_name.startswith("omni."), "Terceros no deben usar el namespace reservado omni.*")

    def test_visual_assets_png_integrity(self):
        """Verifica que icon.png y preview.png sean archivos PNG válidos con cabecera y dimensiones estándar."""
        png_magic = b"\x89PNG\r\n\x1a\n"

        icon_path = os.path.join(EXT_DIR, "data", "icon.png")
        with open(icon_path, "rb") as f:
            content = f.read()
            self.assertTrue(content.startswith(png_magic), "icon.png no es un PNG válido")
            self.assertGreater(len(content), 64, "icon.png está vacío o corrupto")
            w, h = struct.unpack(">II", content[16:24])
            self.assertEqual((w, h), (256, 256), f"icon.png dimensiones inesperadas: {w}x{h}, esperado 256x256")

        preview_path = os.path.join(EXT_DIR, "data", "preview.png")
        with open(preview_path, "rb") as f:
            content = f.read()
            self.assertTrue(content.startswith(png_magic), "preview.png no es un PNG válido")
            self.assertGreater(len(content), 64, "preview.png está vacío o corrupto")
            w, h = struct.unpack(">II", content[16:24])
            self.assertEqual((w, h), (800, 450), f"preview.png dimensiones inesperadas: {w}x{h}, esperado 800x450")

    def test_orlandodorival_lm_chat_import_and_public_function(self):
        """Verifica la importabilidad real del namespace orlandodorival.lm_chat."""
        mod = importlib.import_module("orlandodorival.lm_chat")
        self.assertTrue(hasattr(mod, "some_public_function"))
        self.assertEqual(mod.some_public_function(3), 81)

        # Garantizar que se cargó el módulo real desde el sistema de archivos y no un mock huérfano
        self.assertTrue(hasattr(mod, "__file__"), "El módulo importado carece de __file__")
        self.assertIn("exts", mod.__file__.replace("\\", "/"), "El módulo no proviene de la ruta exts/")
        self.assertTrue(hasattr(mod, "LMChatExtension"), "Falta la clase principal LMChatExtension en el paquete")
        self.assertTrue(hasattr(mod, "__version__"), "Falta __version__ en orlandodorival.lm_chat")
        self.assertTrue(re.match(r"^\d+\.\d+\.\d+", mod.__version__), f"Versión inválida: {mod.__version__}")

    def test_version_synchronization_across_targets(self):
        """Garantiza la sincronización 100% estricta de versiones SemVer 2.0.0."""
        from scripts.release import check_version_sanity
        version = check_version_sanity()
        self.assertTrue(re.match(r"^\d+\.\d+\.\d+", version), f"Versión inválida: {version}")

    def test_citation_metadata_integrity(self):
        """Verifica que CITATION.cff contenga los metadatos de autoría personal de Orlando Dorival sin afiliaciones indebidas."""
        cff_path = os.path.join(REPO_ROOT, "CITATION.cff")
        with open(cff_path, "r", encoding="utf-8") as f:
            cff_text = f.read()
        self.assertIn("Orlando Jesús", cff_text)
        self.assertIn("Dorival Castañeda", cff_text)
        self.assertNotIn("Universidad", cff_text, "El proyecto LM-Chat es 100% personal e independiente")
