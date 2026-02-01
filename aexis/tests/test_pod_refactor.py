from unittest.mock import MagicMock

import pytest
from aexis.core import NetworkContext
from aexis.core.message_bus import MessageBus
from aexis.core.model import Route
from aexis.core.pod import CargoPod, PassengerPod, PodStatus

# Initialize NetworkContext for tests
# Mock data
mock_network_data = {
    "nodes": [
        {
            "id": "001",
            "coordinate": {"x": 0, "y": 0},
            "adj": [{"node_id": "002", "weight": 10.0}],
        },
        {
            "id": "002",
            "coordinate": {"x": 10, "y": 0},
            "adj": [{"node_id": "001", "weight": 10.0}],
        },
    ]
}
# Reset and init singleton
NetworkContext._instance = NetworkContext(mock_network_data)


@pytest.mark.asyncio
async def test_passenger_pod_initialization():
    mock_bus = MagicMock(spec=MessageBus)
    pod = PassengerPod(mock_bus, "pod_test_p")

    # Check specific attributes
    assert pod.capacity == 4
    assert hasattr(pod, "passengers")
    assert isinstance(pod.passengers, list)

    # Check removal of battery
    assert not hasattr(pod, "battery_level")

    # Check state
    state = pod.get_state()
    assert state["type"] == "PassengerPod"
    assert "capacity" in state
    assert state["capacity"]["total"] == 4


@pytest.mark.asyncio
async def test_cargo_pod_initialization():
    mock_bus = MagicMock(spec=MessageBus)
    pod = CargoPod(mock_bus, "pod_test_c")

    # Check specific attributes
    assert pod.weight_capacity == 500.0
    assert hasattr(pod, "cargo")
    assert hasattr(pod, "current_weight")

    # Check removal of battery
    assert not hasattr(pod, "battery_level")

    # Check state
    state = pod.get_state()
    assert state["type"] == "CargoPod"
    assert "weight" in state
    assert state["weight"]["total"] == 500.0


@pytest.mark.asyncio
async def test_pod_route_assignment():
    mock_bus = MagicMock(spec=MessageBus)
    pod = PassengerPod(mock_bus, "pod_test_route")

    # Simulate route assignment command
    route_cmd = {
        "message": {
            "command_type": "AssignRoute",
            "target": "pod_test_route",
            "parameters": {"route": ["station_001", "station_002"]},
        }
    }

    await pod._handle_command(route_cmd)

    assert pod.status == PodStatus.EN_ROUTE
    assert isinstance(pod.current_route, Route)
    assert pod.current_route.stations == ["station_001", "station_002"]


@pytest.mark.asyncio
async def test_network_context_singleton():
    nc1 = NetworkContext.get_instance()
    nc2 = NetworkContext.get_instance()
    assert nc1 is nc2

    dist = nc1.calculate_distance("station_001", "station_001")
    assert dist == 0.0
