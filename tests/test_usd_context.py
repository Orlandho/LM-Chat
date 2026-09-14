# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Unit tests for logic.usd_context.StageContextSerializer.
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from logic.usd_context import StageContextSerializer
from core.interfaces import IStageContextSerializer


class TestStageContextSerializer:
    """Tests for StageContextSerializer class."""

    def test_implements_interface(self):
        """Verify that StageContextSerializer implements IStageContextSerializer."""
        serializer = StageContextSerializer()
        assert isinstance(serializer, IStageContextSerializer)

    @patch("omni.usd.get_context")
    def test_empty_or_unavailable_stage(self, mock_get_context):
        """Test returning empty prims list when stage is unavailable or None."""
        # Case 1: get_context returns None
        mock_get_context.return_value = None
        serializer = StageContextSerializer()
        result_json = serializer.get_stage_context_as_json()
        assert json.loads(result_json) == {"prims": []}

        # Case 2: get_stage returns None
        mock_context = MagicMock()
        mock_context.get_stage.return_value = None
        mock_get_context.return_value = mock_context
        result_json = serializer.get_stage_context_as_json()
        assert json.loads(result_json) == {"prims": []}

    @patch("omni.usd.get_context")
    def test_stage_traversal_with_prims(self, mock_get_context):
        """Test stage traversal with root and nested child prims."""
        # Setup mock stage and prims
        mock_stage = MagicMock()
        mock_context = MagicMock()
        mock_context.get_stage.return_value = mock_stage
        mock_get_context.return_value = mock_context

        # Prim 1: /World (Xform)
        prim1 = MagicMock()
        prim1.IsValid.return_value = True
        prim1.GetPath.return_value = "/World"
        prim1.GetTypeName.return_value = "Xform"
        prim1.GetAttribute.side_effect = lambda attr_name: None

        # Prim 2: /World/Cube (Mesh)
        prim2 = MagicMock()
        prim2.IsValid.return_value = True
        prim2.GetPath.return_value = "/World/Cube"
        prim2.GetTypeName.return_value = "Mesh"

        # Attribute mock for Prim 2
        mock_attr = MagicMock()
        mock_attr.Get.return_value = [0.0, 10.0, 0.0]

        def prim2_get_attr(attr_name):
            if attr_name == "xformOp:translate":
                return mock_attr
            return None

        prim2.GetAttribute.side_effect = prim2_get_attr

        # Prim 3: Deep child /World/Cube/SubMesh/Detail/Extra (Depth = 5)
        prim3 = MagicMock()
        prim3.IsValid.return_value = True
        prim3.GetPath.return_value = "/World/Cube/SubMesh/Detail/Extra"
        prim3.GetTypeName.return_value = "Mesh"
        prim3.GetAttribute.side_effect = lambda attr_name: None

        mock_stage.Traverse.return_value = [prim1, prim2, prim3]

        serializer = StageContextSerializer()

        # Test max_depth = 4 (prim3 with depth 5 should be omitted)
        result_json = serializer.get_stage_context_as_json(max_depth=4)
        data = json.loads(result_json)

        assert "prims" in data
        assert len(data["prims"]) == 2

        assert data["prims"][0]["path"] == "/World"
        assert data["prims"][0]["type"] == "Xform"
        assert data["prims"][0]["visibility"] == "inherited"

        assert data["prims"][1]["path"] == "/World/Cube"
        assert data["prims"][1]["type"] == "Mesh"
        assert data["prims"][1]["attributes_sample"]["xformOp:translate"] == [0.0, 10.0, 0.0]

    @patch("omni.usd.get_context")
    def test_get_prim_summary_existing(self, mock_get_context):
        """Test get_prim_summary for an existing prim."""
        mock_stage = MagicMock()
        mock_context = MagicMock()
        mock_context.get_stage.return_value = mock_stage
        mock_get_context.return_value = mock_context

        mock_prim = MagicMock()
        mock_prim._is_configured = True
        mock_prim.IsValid.return_value = True
        mock_prim.GetTypeName.return_value = "Mesh"
        mock_stage.GetPrimAtPath.return_value = mock_prim

        serializer = StageContextSerializer()
        summary = serializer.get_prim_summary("/World/Cube")

        assert summary["path"] == "/World/Cube"
        assert summary["type"] == "Mesh"
        assert "bounding_box" in summary
        assert "transform_matrix" in summary
        assert "associated_materials" in summary

    @patch("omni.usd.get_context")
    def test_get_prim_summary_non_existing(self, mock_get_context):
        """Test get_prim_summary for a non-existing or invalid prim."""
        mock_stage = MagicMock()
        mock_context = MagicMock()
        mock_context.get_stage.return_value = mock_stage
        mock_get_context.return_value = mock_context

        mock_stage.GetPrimAtPath.return_value = None

        serializer = StageContextSerializer()
        summary = serializer.get_prim_summary("/World/NonExistent")

        assert "error" in summary
        assert summary["path"] == "/World/NonExistent"
