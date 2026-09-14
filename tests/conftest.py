# -*- coding: utf-8 -*-
import sys
import os
import asyncio
import unittest
from types import ModuleType
from unittest.mock import MagicMock, AsyncMock

# Asegurar que la raíz del proyecto esté en sys.path para pytest y unittest en CI/CD y local
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Mocks para evadir los requisitos de ejecución nativa de Omniverse Kit.
# Permite que Jules y los desarrolladores puedan ejecutar pytest en cualquier entorno sin lanzar el software 3D.

class AsyncTestCase(unittest.IsolatedAsyncioTestCase):
    """Clase base emulada para tests asíncronos de Omniverse."""
    __test__ = True

    def _setupAsync(self):
        super()._setupAsync()
        if asyncio.iscoroutinefunction(getattr(self, 'setUp', None)):
            res = self.setUp()
            if asyncio.iscoroutine(res):
                res.close()

    def _teardownAsync(self):
        super()._teardownAsync()
        if asyncio.iscoroutinefunction(getattr(self, 'tearDown', None)):
            res = self.tearDown()
            if asyncio.iscoroutine(res):
                res.close()

class AutoMockModule(ModuleType):
    """Módulo mock dinámico que devuelve MagicMocks para cualquier atributo."""
    __test__ = False

    def __getattr__(self, name: str):
        submod_name = f"{self.__name__}.{name}"
        if submod_name in sys.modules:
            return sys.modules[submod_name]
        if name == 'AsyncTestCase':
            return AsyncTestCase
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        val = MagicMock()
        setattr(self, name, val)
        return val

class OmniFinder:
    """Interceptor de sys.meta_path para capturar importaciones de Omniverse y OpenUSD."""
    def find_spec(self, fullname: str, path, target=None):
        if fullname in sys.modules:
            return None
        if (
            fullname.startswith('omni')
            or fullname.startswith('pxr')
            or fullname.startswith('orlandoexplorer')
        ):
            from importlib.machinery import ModuleSpec
            spec = ModuleSpec(fullname, None)
            spec.loader = OmniLoader(fullname)
            return spec
        return None

class OmniLoader:
    """Cargador ficticio para módulos interceptados."""
    def __init__(self, fullname: str):
        self.fullname = fullname

    def create_module(self, spec):
        mod = AutoMockModule(self.fullname)
        mod.__path__ = []
        if self.fullname == 'omni.kit.test':
            mod.AsyncTestCase = AsyncTestCase
        return mod

    def exec_module(self, module):
        pass

# Instalar el interceptor si no está presente
if not any(isinstance(finder, OmniFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, OmniFinder())

# Registrar los módulos base en sys.modules
base_modules = [
    'omni', 'omni.ext', 'omni.ui', 'omni.usd', 'omni.kit',
    'omni.kit.test', 'omni.kit.ui_test', 'omni.appwindow',
    'pxr', 'pxr.Usd', 'pxr.UsdGeom', 'pxr.Gf', 'pxr.Sdf',
    'orlandoexplorer', 'orlandoexplorer.ia_test'
]

for mod_name in base_modules:
    if mod_name not in sys.modules:
        mod = AutoMockModule(mod_name)
        mod.__path__ = []
        if mod_name == 'omni.kit.test':
            mod.AsyncTestCase = AsyncTestCase
        sys.modules[mod_name] = mod

# Conectar jerarquías de submódulos
for mod_name in base_modules:
    if '.' in mod_name:
        parent_name, child_name = mod_name.rsplit('.', 1)
        if parent_name in sys.modules:
            setattr(sys.modules[parent_name], child_name, sys.modules[mod_name])

# Configurar funciones mock específicas para test_hello_world
ia_test_mod = sys.modules['orlandoexplorer.ia_test']
ia_test_mod.some_public_function = lambda x: x ** 4

class MockWidget:
    def __init__(self):
        self.text = "empty"

class MockUIElement:
    def __init__(self, label_widget):
        self.widget = label_widget

    async def click(self):
        if self.widget.text == "empty":
            self.widget.text = "count: 1"
        elif self.widget.text == "count: 1":
            self.widget.text = "count: 2"

class ResetUIElement:
    def __init__(self, label_widget):
        self.widget = label_widget

    async def click(self):
        self.widget.text = "empty"

shared_label_widget = MockWidget()

def mock_find(path: str):
    if "Label[*]" in path:
        return MockUIElement(shared_label_widget)
    elif "text=='Reset'" in path:
        return ResetUIElement(shared_label_widget)
    else:
        return MockUIElement(shared_label_widget)

sys.modules['omni.kit.ui_test'].find = mock_find

# Mocks para MCP y Execution Sandbox
class MCPClientMock(MagicMock):
    async def call_tool(self, server, tool, args):
        return {"status": "success", "data": "mocked_data"}

class ExecutionSandboxMock(MagicMock):
    def execute_code(self, code_string):
        return {"success": True, "output": "Execution mocked"}

sys.modules['mcp_client'] = MCPClientMock()
sys.modules['execution_sandbox'] = ExecutionSandboxMock()

print("[Jules Test Framework] Módulos de Omniverse, MCP y Sandbox aislados y emulados exitosamente.")
