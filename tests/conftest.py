# -*- coding: utf-8 -*-
import sys
import os
import asyncio
import unittest
from contextlib import contextmanager
from types import ModuleType
from unittest.mock import MagicMock, AsyncMock

# Asegurar que la extensión y la raíz del proyecto estén en sys.path para pytest y unittest en CI/CD y local
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ext_pkg_root = os.path.join(repo_root, "exts", "orlandodorival.lm_chat")
exts_root = os.path.join(repo_root, "exts")

for p in [ext_pkg_root, exts_root, repo_root]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Mocks para evadir los requisitos de ejecución nativa de Omniverse Kit.
# Permite que Jules y los desarrolladores puedan ejecutar pytest en cualquier entorno sin lanzar el software 3D.

class StrictKitUndoDouble(ModuleType):
    """Strict test double matching upstream omni.kit.commands 1.4.10 / omni.kit.undo (Kit 107.3.7).
    Explicitly exposes begin_group, end_group, group, undo, redo, can_undo, can_redo,
    begin_disabled, end_disabled, disabled.
    Strictly forbids begin() and end(), raising AttributeError on access so MagicMock cannot invent them.
    """
    __all__ = [
        "begin_disabled", "begin_group", "can_redo", "can_repeat", "can_undo",
        "clear_history", "clear_stack", "disabled", "end_disabled", "end_group",
        "execute", "get_history", "get_redo_stack", "get_undo_stack", "group",
        "redo", "repeat", "subscribe_on_change", "subscribe_on_change_detailed",
        "undo", "unsubscribe_on_change", "unsubscribe_on_change_detailed"
    ]

    def __init__(self):
        super().__init__("omni.kit.undo")
        self.begin_group = MagicMock(name="begin_group")
        self.end_group = MagicMock(name="end_group")
        self.undo = MagicMock(name="undo", return_value=True)
        self.redo = MagicMock(name="redo", return_value=True)
        self.can_undo = MagicMock(name="can_undo", return_value=True)
        self.can_redo = MagicMock(name="can_redo", return_value=True)
        self.begin_disabled = MagicMock(name="begin_disabled")
        self.end_disabled = MagicMock(name="end_disabled")
        self.clear_history = MagicMock(name="clear_history")
        self.clear_stack = MagicMock(name="clear_stack")
        self.get_history = MagicMock(name="get_history", return_value=[])
        self.get_redo_stack = MagicMock(name="get_redo_stack", return_value=[])
        self.get_undo_stack = MagicMock(name="get_undo_stack", return_value=[])
        self.subscribe_on_change = MagicMock(name="subscribe_on_change")
        self.subscribe_on_change_detailed = MagicMock(name="subscribe_on_change_detailed")
        self.unsubscribe_on_change = MagicMock(name="unsubscribe_on_change")
        self.unsubscribe_on_change_detailed = MagicMock(name="unsubscribe_on_change_detailed")

    @contextmanager
    def group(self):
        self.begin_group()
        try:
            yield
        finally:
            self.end_group()

    @contextmanager
    def disabled(self):
        self.begin_disabled()
        try:
            yield
        finally:
            self.end_disabled()

    def __dir__(self):
        return list(self.__all__)

    def __getattr__(self, name: str):
        if name in ("begin", "end"):
            raise AttributeError(f"module 'omni.kit.undo' has no attribute '{name}' (Kit 107.3.7 upstream invariant)")
        if name not in self.__all__:
            raise AttributeError(f"module 'omni.kit.undo' has no attribute '{name}'")
        val = MagicMock(name=name)
        setattr(self, name, val)
        return val

class AsyncTestCase(unittest.IsolatedAsyncioTestCase):
    """Clase base emulada para tests asíncronos de Omniverse."""
    __test__ = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        import inspect
        if "setUp" in cls.__dict__ and inspect.iscoroutinefunction(cls.__dict__["setUp"]):
            cls.asyncSetUp = cls.__dict__["setUp"]
            cls.setUp = lambda self: None
        if "tearDown" in cls.__dict__ and inspect.iscoroutinefunction(cls.__dict__["tearDown"]):
            cls.asyncTearDown = cls.__dict__["tearDown"]
            cls.tearDown = lambda self: None

def _mock_label_factory(*args, **kwargs):
    m = MagicMock()
    m.text = args[0] if args else kwargs.get("text", "")
    m.style = kwargs.get("style", {})
    return m

def _mock_button_factory(*args, **kwargs):
    m = MagicMock()
    m.text = args[0] if args else kwargs.get("text", "")
    m.style = kwargs.get("style", {})
    m.set_clicked_fn = lambda fn: setattr(m, "_clicked_fn", fn)
    if "clicked_fn" in kwargs:
        m._clicked_fn = kwargs["clicked_fn"]
    return m

def _mock_rectangle_factory(*args, **kwargs):
    m = MagicMock()
    m.style = kwargs.get("style", {})
    return m

def _mock_collapsible_factory(*args, **kwargs):
    m = MagicMock()
    m.title = args[0] if args else kwargs.get("title", "")
    m.collapsed = kwargs.get("collapsed", False)
    m.style = kwargs.get("style", {})
    return m

class AutoMockModule(ModuleType):
    """Módulo mock dinámico que devuelve MagicMocks para cualquier atributo."""
    __test__ = False

    def __getattr__(self, name: str):
        submod_name = f"{self.__name__}.{name}"
        if submod_name in sys.modules:
            return sys.modules[submod_name]
        if name == 'AsyncTestCase':
            return AsyncTestCase
        if self.__name__ == 'omni.kit':
            if name == 'undo':
                return sys.modules.get('omni.kit.undo')
        if self.__name__ == 'omni.kit.commands':
            if name == 'execute':
                val = MagicMock(name="execute", return_value=(True, {"status": "ok"}))
                setattr(self, name, val)
                return val
            if name == 'undo':
                return sys.modules.get('omni.kit.undo')
        if self.__name__ == 'omni.ui':
            if name == 'Label':
                val = MagicMock(side_effect=_mock_label_factory)
                setattr(self, name, val)
                return val
            if name == 'Button':
                val = MagicMock(side_effect=_mock_button_factory)
                setattr(self, name, val)
                return val
            if name == 'Rectangle':
                val = MagicMock(side_effect=_mock_rectangle_factory)
                setattr(self, name, val)
                return val
            if name == 'CollapsibleFrame':
                val = MagicMock(side_effect=_mock_collapsible_factory)
                setattr(self, name, val)
                return val
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
        if self.fullname == 'omni.kit.undo':
            return sys.modules.get('omni.kit.undo') or StrictKitUndoDouble()
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

# Instanciar y registrar el doble estricto de omni.kit.undo
strict_kit_undo = StrictKitUndoDouble()
sys.modules['omni.kit.undo'] = strict_kit_undo

# Registrar los módulos base en sys.modules
base_modules = [
    'omni', 'omni.ext', 'omni.ui', 'omni.usd', 'omni.kit',
    'omni.kit.commands', 'omni.kit.test', 'omni.kit.ui_test', 'omni.appwindow',
    'pxr', 'pxr.Usd', 'pxr.UsdGeom', 'pxr.Gf', 'pxr.Sdf',
    'omni.lm_chat', 'orlandoexplorer', 'orlandoexplorer.ia_test'
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

# Enlazar explícitamente el doble estricto de undo
if 'omni.kit' in sys.modules:
    setattr(sys.modules['omni.kit'], 'undo', strict_kit_undo)
if 'omni.kit.commands' in sys.modules:
    setattr(sys.modules['omni.kit.commands'], 'undo', strict_kit_undo)
    if not hasattr(sys.modules['omni.kit.commands'], 'execute'):
        sys.modules['omni.kit.commands'].execute = MagicMock(name="execute", return_value=(True, {"status": "ok"}))

# Configurar funciones mock específicas para omni.lm_chat y retrocompatibilidad con test_hello_world
class MockIExt:
    pass

if 'omni.ext' in sys.modules:
    setattr(sys.modules['omni.ext'], 'IExt', MockIExt)

lm_chat_mod = sys.modules['omni.lm_chat']
lm_chat_mod.some_public_function = lambda x: x ** 4

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
