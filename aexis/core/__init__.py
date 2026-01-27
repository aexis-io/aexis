import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

model = 'gemini-3-pro-preview'


@dataclass
class NetworkAdjacency:
    node_id: str
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {"node_id": self.node_id, "weight": self.weight}


@dataclass
class NetworkNode:
    id: str
    label: str
    coordinate: Dict[str, float]
    adj: List[NetworkAdjacency] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "coordinate": self.coordinate,
            "adj": [a.to_dict() for a in self.adj]
        }


@dataclass
class Network:
    nodes: List[NetworkNode] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {"nodes": [n.to_dict() for n in self.nodes]}


def load_network_data(path: str) -> Optional[Dict[str, Any]]:
    """Load network topology from JSON file and return as raw dict."""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Network file not found: {path}")
        return None
    except Exception as e:
        print(f"Error loading network: {e}")
        return None
