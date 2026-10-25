# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Pruebas automatizadas para el Módulo de Políticas y Gobernanza de Agentes (SpatialSecurityPolicy).
Valida:
- Inspección estática AST de imports prohibidos y llamadas a builtins peligrosos.
- Detección de bucles infinitos y límites de iteraciones.
- Invariante de prims protegidos del sistema en OpenUSD.
- Admisión de código OpenUSD legítimo y seguro.
"""

import pytest
from core.policies import SpatialSecurityPolicy, AgentPolicyConfig


class TestSpatialSecurityPolicy:
    """Suite de pruebas de gobernanza y seguridad de código para agentes espaciales."""

    def test_valid_openusd_code_allowed(self):
        """Código legítimo de creación y manipulación en OpenUSD es aprobado."""
        policy = SpatialSecurityPolicy()
        safe_code = """
import omni.usd
from pxr import Usd, UsdGeom, Gf

stage = omni.usd.get_context().get_stage()
cube = UsdGeom.Cube.Define(stage, '/World/Cube')
cube.AddTranslateOp().Set(Gf.Vec3d(0.0, 10.0, 0.0))
"""
        valid, err = policy.validate_code(safe_code)
        assert valid is True
        assert err is None

    def test_empty_or_invalid_type_rejected(self):
        """Rechaza cargas vacías, espacios en blanco o tipos no válidos."""
        policy = SpatialSecurityPolicy()
        valid, err = policy.validate_code("")
        assert valid is False
        assert "non-empty string" in err

        valid, err = policy.validate_code("   \n\t  ")
        assert valid is False

    def test_code_size_limit_exceeded(self):
        """Rechaza payloads que exceden el tamaño máximo configurado para prevenir DoS."""
        config = AgentPolicyConfig(max_code_size=100)
        policy = SpatialSecurityPolicy(config=config)
        large_code = "# Comment line\n" * 15

        valid, err = policy.validate_code(large_code)
        assert valid is False
        assert "exceeds maximum allowed limit" in err

    def test_syntax_error_rejected(self):
        """Detecta y rechaza errores de sintaxis antes de la ejecución."""
        policy = SpatialSecurityPolicy()
        invalid_syntax = "def broken_func(:\n    pass"

        valid, err = policy.validate_code(invalid_syntax)
        assert valid is False
        assert "Syntax Error" in err

    def test_forbidden_imports_blocked(self):
        """Bloquea imports de módulos prohibidos mediante análisis AST (shutil, subprocess, socket, etc.)."""
        policy = SpatialSecurityPolicy()

        cases = [
            "import subprocess\nsubprocess.run(['ls'])",
            "import socket\ns = socket.socket()",
            "from shutil import rmtree\nrmtree('/tmp')",
            "import urllib.request",
            "import requests\nrequests.get('http://example.com')",
        ]

        for code in cases:
            valid, err = policy.validate_code(code)
            assert valid is False, f"El código debió ser bloqueado: {code}"
            assert "Security Policy Violation" in err
            assert "forbidden module" in err

    def test_forbidden_builtins_blocked(self):
        """Bloquea funciones built-in peligrosas como eval y compile."""
        policy = SpatialSecurityPolicy()

        eval_code = "result = eval('2 + 2')"
        valid, err = policy.validate_code(eval_code)
        assert valid is False
        assert "forbidden builtin function 'eval()'" in err

        compile_code = "c = compile('pass', '', 'exec')"
        valid, err = policy.validate_code(compile_code)
        assert valid is False
        assert "forbidden builtin function 'compile()'" in err

    def test_forbidden_os_calls_blocked(self):
        """Bloquea llamadas directas a métodos peligrosos de os (system, remove, popen)."""
        policy = SpatialSecurityPolicy()

        cases = [
            "import os\nos.system('calc')",
            "import os\nos.remove('/path/file.usd')",
            "import os\nos.popen('whoami')",
            "import os\ngetattr(os, 'system')('calc')",
            "import os\nfn = getattr(os, 'remove')\nfn('/path/file.usd')",
        ]

        for code in cases:
            valid, err = policy.validate_code(code)
            assert valid is False
            assert "Dangerous system operation" in err

    def test_infinite_loop_detection(self):
        """Detecta bucles 'while True' sin cláusula break."""
        policy = SpatialSecurityPolicy()

        infinite_loop = """
while True:
    print('bucle infinito')
"""
        valid, err = policy.validate_code(infinite_loop)
        assert valid is False
        assert "infinite loop detected" in err

        # Bucle con break debe ser permitido
        loop_with_break = """
count = 0
while True:
    count += 1
    if count > 5:
        break
"""
        valid, err = policy.validate_code(loop_with_break)
        assert valid is True
        assert err is None

    def test_loop_iteration_limit_exceeded(self):
        """Bloquea bucles 'for' que iteran sobre rangos desmedidos previniendo bloqueo de la UI."""
        config = AgentPolicyConfig(max_loop_iterations=5000)
        policy = SpatialSecurityPolicy(config=config)

        excessive_for = """
for i in range(100000):
    pass
"""
        valid, err = policy.validate_code(excessive_for)
        assert valid is False
        assert "Loop iteration limit" in err

    def test_protected_system_prims_guardrails(self):
        """Protege prims del sistema Omniverse (/OmniverseKit_Root, /Render) de eliminación o manipulación."""
        policy = SpatialSecurityPolicy()

        assert policy.is_prim_protected("/OmniverseKit_Root") is True
        assert policy.is_prim_protected("/OmniverseKit_Root/StageContext") is True
        assert policy.is_prim_protected("/Render") is True
        assert policy.is_prim_protected("/Render/ActiveCamera") is True
        assert policy.is_prim_protected("/World/Props/Chair") is False

        # Intentos destructivos sobre prims protegidos son bloqueados
        destructive_code = """
stage = omni.usd.get_context().get_stage()
stage.RemovePrim('/OmniverseKit_Root')
"""
        valid, err = policy.validate_code(destructive_code)
        assert valid is False
        assert "system-protected prim path" in err

    def test_protected_system_prims_mutation_and_creation_blocked(self):
        """Bloquea cualquier intento de crear, definir o mutar sobre prims protegidos del sistema."""
        policy = SpatialSecurityPolicy()

        cases = [
            "stage.DefinePrim('/OmniverseKit_Root/Hacked', 'Cube')",
            "stage.CreatePrim('/Render/NewCam', 'Camera')",
            "stage.OverridePrim('/World/System/Config')",
        ]
        for code in cases:
            valid, err = policy.validate_code(code)
            assert valid is False, f"Debió bloquearse: {code}"
            assert "system-protected prim path" in err

    def test_prim_creation_limit_in_loops_enforced(self):
        """Bloquea bucles que intentan crear una cantidad de prims mayor a max_prims_creation_limit."""
        config = AgentPolicyConfig(max_prims_creation_limit=100)
        policy = SpatialSecurityPolicy(config=config)

        excessive_creation = """
stage = omni.usd.get_context().get_stage()
for i in range(150):
    stage.DefinePrim(f'/World/Cube_{i}', 'Cube')
"""
        valid, err = policy.validate_code(excessive_creation)
        assert valid is False
        assert "Prim creation limit in loop (150 > 100) exceeded" in err

    def test_exec_and_import_builtins_blocked(self):
        """Bloquea llamadas a exec() y __import__() dinámico."""
        policy = SpatialSecurityPolicy()

        exec_code = "exec('2 + 2')"
        valid, err = policy.validate_code(exec_code)
        assert valid is False
        assert "forbidden builtin function 'exec()'" in err

        import_code = "mod = __import__('os')"
        valid, err = policy.validate_code(import_code)
        assert valid is False
        assert "forbidden builtin function '__import__()'" in err

    def test_usd_controller_group_prims_policy_limits(self):
        """Verifica que USDController.group_prims respete el límite de prims y rutas destino protegidas."""
        from logic.usd_controller import USDController
        controller = USDController()

        # Probar intento de agrupar bajo una ruta protegida
        res_prot = controller.group_prims(["/World/Cube1"], "/OmniverseKit_Root")
        assert res_prot["success"] is False
        assert "está protegida por el sistema" in res_prot["error_msg"]

        # Probar intento de agrupar más prims del límite
        many_prims = [f"/World/Prim_{i}" for i in range(501)]
        res_limit = controller.group_prims(many_prims, "/World/PropsGroup")
        assert res_limit["success"] is False
        assert "excede el límite permitido" in res_limit["error_msg"]
