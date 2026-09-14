import sys
from unittest.mock import MagicMock

# Mocks para evadir los requisitos de ejecución nativa de Omniverse Kit.
# Permite que Jules pueda ejecutar pytest en cualquier entorno (CI/CD o local) sin lanzar el software 3D.
class OmniMock(MagicMock):
    pass

class PxrMock(MagicMock):
    pass

sys.modules['omni'] = OmniMock()
sys.modules['omni.ext'] = OmniMock()
sys.modules['omni.ui'] = OmniMock()
sys.modules['omni.usd'] = OmniMock()
sys.modules['omni.kit'] = OmniMock()
sys.modules['omni.kit.test'] = OmniMock()
sys.modules['omni.kit.ui_test'] = OmniMock()

sys.modules['pxr'] = PxrMock()
sys.modules['pxr.Usd'] = PxrMock()
sys.modules['pxr.UsdGeom'] = PxrMock()
sys.modules['pxr.Gf'] = PxrMock()
sys.modules['pxr.Sdf'] = PxrMock()

print("[Jules Test Framework] Módulos de Omniverse y OpenUSD interceptados y emulados exitosamente.")
