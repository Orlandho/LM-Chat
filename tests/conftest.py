import sys
from unittest.mock import MagicMock

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
    def get_context(self):
        ctx = MagicMock()
        ctx.get_stage.return_value = MagicMock()
        return ctx
    def get_stage(self):
        return MagicMock()

class MCPClientMock(MagicMock):
    """Mock especializado para llamadas a servidores MCP (Lectura de documentos, APIs)."""
    async def call_tool(self, server, tool, args):
        return {"status": "success", "data": "mocked_data"}

class ExecutionSandboxMock(MagicMock):
    """Mock especializado para el Execution Sandbox (Self-Healing)."""
    def execute_code(self, code_string):
        return {"success": True, "output": "Execution mocked"}

# Inyección de módulos simulados al sistema
sys.modules['omni'] = MagicMock()
sys.modules['omni.ext'] = MagicMock()
sys.modules['omni.ui'] = OmniUIMock()
sys.modules['omni.usd'] = UsdContextMock()
sys.modules['omni.kit'] = MagicMock()
sys.modules['omni.kit.test'] = MagicMock()
sys.modules['omni.kit.ui_test'] = MagicMock()
sys.modules['omni.appwindow'] = MagicMock()
sys.modules['orlandoexplorer'] = MagicMock()
sys.modules['orlandoexplorer.ia_test'] = MagicMock()

sys.modules['pxr'] = MagicMock()
sys.modules['pxr.Usd'] = UsdContextMock()
sys.modules['pxr.UsdGeom'] = MagicMock()

sys.modules['mcp_client'] = MCPClientMock()
sys.modules['execution_sandbox'] = ExecutionSandboxMock()

print("[Jules Test Framework] Módulos de Omniverse, MCP y Sandbox aislados y emulados exitosamente.")
