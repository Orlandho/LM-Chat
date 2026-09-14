# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Célula Robótica Autónoma de Manufactura y Clasificación con Gemelo Digital
Generado mediante Google Gemini 3.6 Flash (Free Tier) vía OmniAgent Inference Router.

Compatible con NVIDIA Omniverse Kit SDK (Isaac Sim, Code, Create).
Utiliza OpenUSD (pxr), NVIDIA PhysX (pxr.UsdPhysics, pxr.PhysxSchema) y sombreado PBR (pxr.UsdShade).
"""

import omni.usd
import omni.kit.commands
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, UsdLux, PhysxSchema, Gf, Sdf, Vt


def create_pbr_material(stage, path, name, rgb, metallic=0.0, roughness=0.5):
    """Crea un material PBR basado en UsdPreviewSurface."""
    mat_path = f"{path}/{name}"
    material = UsdShade.Material.Define(stage, mat_path)
    pbr_shader = UsdShade.Shader.Define(stage, f"{mat_path}/PBRShader")

    pbr_shader.CreateIdAttr("UsdPreviewSurface")
    pbr_shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    pbr_shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
    pbr_shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)

    material.CreateSurfaceOutput().ConnectToSource(pbr_shader.ConnectableAPI(), "surface")
    return material


def apply_physics_material_properties(stage, prim, static_friction, dynamic_friction, restitution):
    """Aplica fricción y restitución mediante UsdPhysics.MaterialAPI."""
    mat_path = prim.GetPath().AppendChild("PhysicsMaterial")
    phys_mat = UsdPhysics.MaterialAPI.Apply(stage.DefinePrim(mat_path, "Material"))
    phys_mat.CreateStaticFrictionAttr().Set(static_friction)
    phys_mat.CreateDynamicFrictionAttr().Set(dynamic_friction)
    phys_mat.CreateRestitutionAttr().Set(restitution)

    UsdShade.MaterialBindingAPI.Apply(prim.GetPrim()).Bind(
        UsdShade.Material(stage.GetPrimAtPath(mat_path)),
        UsdShade.Tokens.strongerThanDescendants,
    )


def build_autonomous_cell(stage=None):
    """
    Construye la escena completa de la célula robótica industrial en Omniverse.
    """
    if stage is None:
        stage = omni.usd.get_context().get_stage()

    print("[Omniverse Architect] Iniciando construcción de la escena industrial USD...")

    # Configuración de unidades métricas del Stage
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)

    # Root Group
    world_prim = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world_prim.GetPrim())

    # 1. MATERIALES PBR
    materials_scope = stage.DefinePrim("/World/Materials", "Scope")
    mat_aluminum = create_pbr_material(stage, "/World/Materials", "AerospaceAluminum", (0.8, 0.82, 0.85), 0.9, 0.2)
    mat_rubber = create_pbr_material(stage, "/World/Materials", "SyntheticRubber", (0.05, 0.05, 0.05), 0.0, 0.85)
    mat_blue = create_pbr_material(stage, "/World/Materials", "AnodizedBlue", (0.05, 0.3, 0.85), 0.7, 0.3)
    mat_orange = create_pbr_material(stage, "/World/Materials", "AlertOrange", (1.0, 0.25, 0.0), 0.1, 0.4)

    # 2. ILUMINACIÓN Y ENTORNO
    lighting_scope = stage.DefinePrim("/World/Lighting", "Scope")
    dome_light = UsdLux.DomeLight.Define(stage, "/World/Lighting/DomeLight")
    dome_light.CreateIntensityAttr().Set(1000.0)
    dome_light.CreateColorAttr().Set(Gf.Vec3f(0.95, 0.95, 1.0))

    rect_light = UsdLux.RectLight.Define(stage, "/World/Lighting/WorkstationLight")
    rect_light.CreateIntensityAttr().Set(25000.0)
    rect_light.CreateWidthAttr().Set(3.0)
    rect_light.CreateHeightAttr().Set(3.0)
    rect_light.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 4.0))

    # 3. SUELO INDUSTRIAL (FactoryFloor)
    floor_path = "/World/FactoryFloor"
    floor_cube = UsdGeom.Cube.Define(stage, floor_path)
    floor_cube.CreateSizeAttr().Set(1.0)
    floor_cube.AddScaleOp().Set(Gf.Vec3d(10.0, 10.0, 0.1))
    floor_cube.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, -0.05))

    UsdPhysics.RigidBodyAPI.Apply(floor_cube.GetPrim())
    UsdPhysics.CollisionAPI.Apply(floor_cube.GetPrim())
    apply_physics_material_properties(stage, floor_cube.GetPrim(), static_friction=0.7, dynamic_friction=0.6, restitution=0.1)
    UsdShade.MaterialBindingAPI.Apply(floor_cube.GetPrim()).Bind(mat_aluminum)

    # 4. SISTEMA DE TRANSPORTE (ConveyorSystem)
    conveyor_root = UsdGeom.Xform.Define(stage, "/World/ConveyorSystem")

    # Frame
    frame_path = "/World/ConveyorSystem/Frame"
    frame = UsdGeom.Cube.Define(stage, frame_path)
    frame.CreateSizeAttr().Set(1.0)
    frame.AddScaleOp().Set(Gf.Vec3d(0.8, 4.0, 0.6))
    frame.AddTranslateOp().Set(Gf.Vec3d(1.0, 0.0, 0.3))
    UsdPhysics.CollisionAPI.Apply(frame.GetPrim())
    UsdShade.MaterialBindingAPI.Apply(frame.GetPrim()).Bind(mat_aluminum)

    # Belt Surface Dinámica con PhysX
    belt_path = "/World/ConveyorSystem/Belt"
    belt = UsdGeom.Cube.Define(stage, belt_path)
    belt.CreateSizeAttr().Set(1.0)
    belt.AddScaleOp().Set(Gf.Vec3d(0.6, 4.0, 0.05))
    belt.AddTranslateOp().Set(Gf.Vec3d(1.0, 0.0, 0.625))

    belt_rb = UsdPhysics.RigidBodyAPI.Apply(belt.GetPrim())
    belt_rb.CreateKinematicEnabledAttr().Set(True)
    UsdPhysics.CollisionAPI.Apply(belt.GetPrim())

    conveyor_api = PhysxSchema.PhysxConveyorBeltAPI.Apply(belt.GetPrim())
    conveyor_api.CreateVelocityAttr().Set(Gf.Vec3f(0.0, 0.6, 0.0))  # 0.6 m/s en eje Y
    conveyor_api.CreateEnabledAttr().Set(True)

    apply_physics_material_properties(stage, belt.GetPrim(), static_friction=0.9, dynamic_friction=0.85, restitution=0.0)
    UsdShade.MaterialBindingAPI.Apply(belt.GetPrim()).Bind(mat_rubber)

    # 5. BRAZO ROBÓTICO ARTICULADO (RoboticArm)
    arm_root = UsdGeom.Xform.Define(stage, "/World/RoboticArm")
    arm_root.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.0))
    UsdPhysics.ArticulationRootAPI.Apply(arm_root.GetPrim())

    # Base Link
    base_path = "/World/RoboticArm/BaseLink"
    base_link = UsdGeom.Cylinder.Define(stage, base_path)
    base_link.CreateHeightAttr().Set(0.4)
    base_link.CreateRadiusAttr().Set(0.2)
    base_link.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.2))
    UsdPhysics.RigidBodyAPI.Apply(base_link.GetPrim())
    UsdPhysics.CollisionAPI.Apply(base_link.GetPrim())
    UsdShade.MaterialBindingAPI.Apply(base_link.GetPrim()).Bind(mat_aluminum)

    # Link 1 (Upper Arm)
    link1_path = "/World/RoboticArm/Link1_Arm"
    link1 = UsdGeom.Cylinder.Define(stage, link1_path)
    link1.CreateHeightAttr().Set(0.8)
    link1.CreateRadiusAttr().Set(0.08)
    link1.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.8))
    UsdPhysics.RigidBodyAPI.Apply(link1.GetPrim())
    UsdPhysics.CollisionAPI.Apply(link1.GetPrim())
    UsdShade.MaterialBindingAPI.Apply(link1.GetPrim()).Bind(mat_aluminum)

    # Joint 1: Revoluta Base -> Link1 (Eje Z)
    j1_path = "/World/RoboticArm/Joint1_Shoulder"
    joint1 = UsdPhysics.RevoluteJoint.Define(stage, j1_path)
    joint1.CreateAxisAttr().Set("Z")
    joint1.CreateBody0Rel().SetTargets([base_path])
    joint1.CreateBody1Rel().SetTargets([link1_path])
    joint1.CreateLocalPos0Attr().Set(Gf.Vec3f(0.0, 0.0, 0.2))
    joint1.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0, 0.0, -0.4))

    j1_drive = UsdPhysics.DriveAPI.Apply(joint1.GetPrim(), "angular")
    j1_drive.CreateStiffnessAttr().Set(1e6)
    j1_drive.CreateDampingAttr().Set(1e4)
    j1_drive.CreateTargetPositionAttr().Set(0.0)

    # Link 2 (Forearm)
    link2_path = "/World/RoboticArm/Link2_Forearm"
    link2 = UsdGeom.Cylinder.Define(stage, link2_path)
    link2.CreateHeightAttr().Set(0.6)
    link2.CreateRadiusAttr().Set(0.06)
    link2.AddTranslateOp().Set(Gf.Vec3d(0.4, 0.0, 1.2))
    link2.AddRotateXYZOp().Set(Gf.Vec3d(0.0, 90.0, 0.0))
    UsdPhysics.RigidBodyAPI.Apply(link2.GetPrim())
    UsdPhysics.CollisionAPI.Apply(link2.GetPrim())
    UsdShade.MaterialBindingAPI.Apply(link2.GetPrim()).Bind(mat_aluminum)

    # Joint 2: Revoluta Link1 -> Link2 (Eje Y)
    j2_path = "/World/RoboticArm/Joint2_Elbow"
    joint2 = UsdPhysics.RevoluteJoint.Define(stage, j2_path)
    joint2.CreateAxisAttr().Set("Y")
    joint2.CreateBody0Rel().SetTargets([link1_path])
    joint2.CreateBody1Rel().SetTargets([link2_path])
    joint2.CreateLocalPos0Attr().Set(Gf.Vec3f(0.0, 0.0, 0.4))
    joint2.CreateLocalPos1Attr().Set(Gf.Vec3f(-0.3, 0.0, 0.0))

    j2_drive = UsdPhysics.DriveAPI.Apply(joint2.GetPrim(), "angular")
    j2_drive.CreateStiffnessAttr().Set(1e6)
    j2_drive.CreateDampingAttr().Set(1e4)
    j2_drive.CreateTargetPositionAttr().Set(45.0)

    # End Effector Tool (Gripper Base)
    tool_path = "/World/RoboticArm/EndEffector_Tool"
    tool = UsdGeom.Cube.Define(stage, tool_path)
    tool.CreateSizeAttr().Set(0.12)
    tool.AddTranslateOp().Set(Gf.Vec3d(0.7, 0.0, 1.2))
    UsdPhysics.RigidBodyAPI.Apply(tool.GetPrim())
    UsdPhysics.CollisionAPI.Apply(tool.GetPrim())
    UsdShade.MaterialBindingAPI.Apply(tool.GetPrim()).Bind(mat_aluminum)

    # Joint 3: Prismática (Gripper Actuator)
    j3_path = "/World/RoboticArm/Joint3_Gripper"
    joint3 = UsdPhysics.PrismaticJoint.Define(stage, j3_path)
    joint3.CreateAxisAttr().Set("X")
    joint3.CreateBody0Rel().SetTargets([link2_path])
    joint3.CreateBody1Rel().SetTargets([tool_path])
    joint3.CreateLocalPos0Attr().Set(Gf.Vec3f(0.3, 0.0, 0.0))
    joint3.CreateLocalPos1Attr().Set(Gf.Vec3f(-0.06, 0.0, 0.0))
    joint3.CreateLowerLimitAttr().Set(0.0)
    joint3.CreateUpperLimitAttr().Set(0.2)

    j3_drive = UsdPhysics.DriveAPI.Apply(joint3.GetPrim(), "linear")
    j3_drive.CreateStiffnessAttr().Set(5e5)
    j3_drive.CreateDampingAttr().Set(1e3)
    j3_drive.CreateTargetPositionAttr().Set(0.05)

    # 6. SENSORES (Optical Detection Trigger Zone)
    trigger_path = "/World/Sensors/OpticalTrigger"
    trigger = UsdGeom.Cube.Define(stage, trigger_path)
    trigger.CreateSizeAttr().Set(1.0)
    trigger.AddScaleOp().Set(Gf.Vec3d(0.8, 0.2, 0.4))
    trigger.AddTranslateOp().Set(Gf.Vec3d(1.0, 0.0, 0.85))

    UsdPhysics.CollisionAPI.Apply(trigger.GetPrim())
    PhysxSchema.PhysxTriggerAPI.Apply(trigger.GetPrim())
    trigger.CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)

    # 7. CÁMARA DE INSPECCIÓN
    cam_path = "/World/Camera_Inspection"
    cam = UsdGeom.Camera.Define(stage, cam_path)
    cam.AddTranslateOp().Set(Gf.Vec3d(2.5, 2.5, 2.5))
    cam.AddRotateXYZOp().Set(Gf.Vec3d(55.0, 0.0, 135.0))
    cam.CreateFocalLengthAttr().Set(35.0)

    # 8. PIEZAS DINÁMICAS DE PRUEBA (Payloads)
    payload_blue = UsdGeom.Cube.Define(stage, "/World/DynamicPayloads/Payload_Blue")
    payload_blue.CreateSizeAttr().Set(0.15)
    payload_blue.AddTranslateOp().Set(Gf.Vec3d(1.0, -1.5, 0.8))
    UsdPhysics.RigidBodyAPI.Apply(payload_blue.GetPrim())
    UsdPhysics.MassAPI.Apply(payload_blue.GetPrim()).CreateMassAttr().Set(0.5)
    UsdPhysics.CollisionAPI.Apply(payload_blue.GetPrim())
    apply_physics_material_properties(stage, payload_blue.GetPrim(), 0.6, 0.5, 0.1)
    UsdShade.MaterialBindingAPI.Apply(payload_blue.GetPrim()).Bind(mat_blue)

    print("✅ Célula robótica industrial con física PhysX y OpenUSD generada exitosamente en /World.")


if __name__ == "__main__":
    build_autonomous_cell()
