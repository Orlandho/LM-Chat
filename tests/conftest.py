import sys
import types
from unittest.mock import MagicMock

# Dynamic module dict that returns MagicMock for missing attributes
class DynamicModule(types.ModuleType):
    def __getattr__(self, name):
        return MagicMock()

# Mocks Avanzados para Tests Unitarios Aislados (Swarm / Jules Concurrente)
# Cada mock expone un comportamiento específico para evitar colisiones entre issues paralelos.

class OmniUIMock(MagicMock):
    """Mock especializado para omni.ui (GUI)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.Window = MagicMock
        self.Frame = MagicMock
        self.VStack = MagicMock
        self.HStack = MagicMock
        self.Button = MagicMock
        self.Label = MagicMock

class UsdContextMock(MagicMock):
    """Mock especializado para pxr.Usd y omni.usd (Contexto USD)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._context = MagicMock()
        self._stage = MagicMock()
        self._context.get_stage.return_value = self._stage
    def get_context(self):
        return self._context
    def get_stage(self):
        return self._stage

class MCPClientMock(MagicMock):
    """Mock especializado para llamadas a servidores MCP (Lectura de documentos, APIs)."""
    async def call_tool(self, server, tool, args):
        return {"status": "success", "data": "mocked_data"}

class ExecutionSandboxMock(MagicMock):
    """Mock especializado para el Execution Sandbox (Self-Healing)."""
    def execute_code(self, code_string):
        return {"success": True, "output": "Execution mocked"}

# Custom sys.meta_path finder/loader to intercept orlandoexplorer module
class OrlandoExplorerFinder:
    def find_spec(self, fullname, path, target=None):
        if fullname.startswith("orlandoexplorer"):
            from importlib.machinery import ModuleSpec
            return ModuleSpec(fullname, OrlandoExplorerLoader())
        return None

class OrlandoExplorerLoader:
    def create_module(self, spec):
        mod = DynamicModule(spec.name)
        mod.ia_test = MagicMock()
        return mod

    def exec_module(self, module):
        pass

sys.meta_path.insert(0, OrlandoExplorerFinder())

# Inyección de módulos simulados al sistema
omni_mock = DynamicModule('omni')
omni_ext_mock = MagicMock()
omni_ui_mock = OmniUIMock()
omni_usd_mock = UsdContextMock()
omni_kit_mock = DynamicModule('omni.kit')

omni_mock.ext = omni_ext_mock
omni_mock.ui = omni_ui_mock
omni_mock.usd = omni_usd_mock
omni_mock.kit = omni_kit_mock
omni_mock.appwindow = MagicMock()

sys.modules['omni'] = omni_mock
sys.modules['omni.ext'] = omni_ext_mock
sys.modules['omni.ui'] = omni_ui_mock
sys.modules['omni.usd'] = omni_usd_mock
sys.modules['omni.kit'] = omni_kit_mock
sys.modules['omni.kit.test'] = MagicMock()
sys.modules['omni.kit.ui_test'] = MagicMock()
sys.modules['omni.appwindow'] = omni_mock.appwindow

pxr_mock = DynamicModule('pxr')
pxr_usd_mock = UsdContextMock()
pxr_usdgeom_mock = MagicMock()
pxr_usdshade_mock = MagicMock()
pxr_sdf_mock = MagicMock()
pxr_gf_mock = MagicMock()

pxr_mock.Usd = pxr_usd_mock
pxr_mock.UsdGeom = pxr_usdgeom_mock
pxr_mock.UsdShade = pxr_usdshade_mock
pxr_mock.Sdf = pxr_sdf_mock
pxr_mock.Gf = pxr_gf_mock

sys.modules['pxr'] = pxr_mock
sys.modules['pxr.Usd'] = pxr_usd_mock
sys.modules['pxr.UsdGeom'] = pxr_usdgeom_mock
sys.modules['pxr.UsdShade'] = pxr_usdshade_mock
sys.modules['pxr.Sdf'] = pxr_sdf_mock
sys.modules['pxr.Gf'] = pxr_gf_mock

sys.modules['mcp_client'] = MCPClientMock()
sys.modules['execution_sandbox'] = ExecutionSandboxMock()

print("[Jules Test Framework] Módulos de Omniverse, MCP y Sandbox aislados y emulados exitosamente.")
