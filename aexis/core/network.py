import json
import math
import os
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

@dataclass
class NetworkAdjacency:
    node_id: str
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "weight": self.weight}


@dataclass
class NetworkNode:
    id: str
    label: str
    coordinate: dict[str, float]
    adj: list[NetworkAdjacency] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "coordinate": self.coordinate,
            "adj": [a.to_dict() for a in self.adj],
        }


@dataclass
class Network:
    nodes: list[NetworkNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": [n.to_dict() for n in self.nodes]}


def load_network_data(path: str) -> dict[str, Any] | None:
    """Load network topology from JSON file and return as raw dict."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Network file not found: {path}")
        return None
    except Exception as e:
        print(f"Error loading network: {e}")
        return None


class NetworkContext:
    """Centralized context for network state and topology"""

    _instance = None

    def __init__(self, network_data: dict | None = None):
        self.network_graph = nx.Graph()
        self.station_positions = {}
        # Map station_id -> Station object (populated by system)
        self.stations = {}

        if not network_data:
            # Attempt to load from default path
            try:
                # Try finding the file relative to current working dir or package
                # Assuming CWD is project root usually
                path = os.getenv("AEXIS_NETWORK_DATA", "aexis/network.json")
                if os.path.exists(path):
                    network_data = load_network_data(path)
                else:
                    # Try looking in package
                    import pkg_resources

                    # Example fallback
                    if pkg_resources.resource_exists(__name__, "network.json"):
                        pass
            except Exception as e:
                print(f"Failed to auto-load network data: {e}")

        if network_data:
            self._initialize_from_data(network_data)
        else:
            # Just init empty, do not hardcode.
            print("Warning: NetworkContext initialized with empty network.")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set_instance(cls, instance):
        cls._instance = instance

    def _initialize_from_data(self, data: dict):
        """Initialize graph from loaded data"""
        if "nodes" not in data:
            return

        for node in data["nodes"]:
            station_id = f"station_{node['id']}"

            # Position
            coord = node.get("coordinate", {"x": 0, "y": 0})
            pos = (coord["x"], coord["y"])
            self.station_positions[station_id] = pos
            self.network_graph.add_node(station_id, pos=pos)

            # Edges
            for adj in node.get("adj", []):
                target_id = f"station_{adj['node_id']}"
                weight = adj.get("weight", 1.0)
                # We'll calculate actual distance for weight if pos is valid, else use abstract weight
                # For now just adding edge, weight update effectively happens if we recalc
                self.network_graph.add_edge(
                    station_id, target_id, weight=weight)

        # Recalculate weights based on Euclidean distance for consistency
        for u, v in self.network_graph.edges():
            dist = self.calculate_distance(u, v)
            if dist > 0:
                self.network_graph[u][v]["weight"] = dist

    def _initialize_default(self):
        """Deprecated: Logic removed to favor data-driven initialization"""
        pass

    def calculate_distance(self, station1: str, station2: str) -> float:
        """Calculate Euclidean distance between stations"""
        pos1 = self.station_positions.get(station1, (0, 0))
        pos2 = self.station_positions.get(station2, (0, 0))
        return math.sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)

    def get_route_distance(self, route: list[str]) -> float:
        """Calculate total distance for a route"""
        total_distance = 0.0
        for i in range(len(route) - 1):
            try:
                # Use NetworkX shortest path for accurate distances if direct edge doesn't exist?
                # Actually, route is usually a sequence of connected stations.
                # If they are adjacent, use edge weight.
                if self.network_graph.has_edge(route[i], route[i + 1]):
                    total_distance += self.network_graph[route[i]][route[i + 1]][
                        "weight"
                    ]
                else:
                    # Fallback or strict error? Fallback to Euclidean
                    total_distance += self.calculate_distance(
                        route[i], route[i + 1])
            except Exception:
                total_distance += self.calculate_distance(
                    route[i], route[i + 1])
        return total_distance
