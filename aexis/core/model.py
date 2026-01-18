from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import uuid4


class PodStatus(Enum):
    IDLE = "idle"
    LOADING = "loading"
    EN_ROUTE = "en_route"
    UNLOADING = "unloading"
    MAINTENANCE = "maintenance"


class StationStatus(Enum):
    OPERATIONAL = "operational"
    CONGESTED = "congested"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


class Priority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4
    CRITICAL = 5


@dataclass
class Event:
    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PassengerArrival(Event):
    event_type: str = "PassengerArrival"
    passenger_id: str = ""
    station_id: str = ""
    destination: str = ""
    priority: int = Priority.NORMAL.value
    group_size: int = 1
    special_needs: List[str] = field(default_factory=list)
    wait_time_limit: int = 30  # minutes


@dataclass
class PassengerPickedUp(Event):
    event_type: str = "PassengerPickedUp"
    passenger_id: str = ""
    pod_id: str = ""
    station_id: str = ""
    pickup_time: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PassengerDelivered(Event):
    event_type: str = "PassengerDelivered"
    passenger_id: str = ""
    pod_id: str = ""
    station_id: str = ""
    delivery_time: datetime = field(default_factory=datetime.utcnow)
    total_travel_time: int = 0  # seconds
    satisfaction_score: float = 0.0


@dataclass
class CargoRequest(Event):
    event_type: str = "CargoRequest"
    request_id: str = ""
    origin: str = ""
    destination: str = ""
    weight: float = 0.0
    volume: float = 0.0
    priority: int = Priority.NORMAL.value
    hazardous: bool = False
    temperature_controlled: bool = False
    deadline: Optional[datetime] = None


@dataclass
class CargoLoaded(Event):
    event_type: str = "CargoLoaded"
    request_id: str = ""
    pod_id: str = ""
    station_id: str = ""
    load_time: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CargoDelivered(Event):
    event_type: str = "CargoDelivered"
    request_id: str = ""
    pod_id: str = ""
    station_id: str = ""
    delivery_time: datetime = field(default_factory=datetime.utcnow)
    condition: str = "good"
    on_time: bool = True


@dataclass
class PodStatusUpdate(Event):
    event_type: str = "PodStatusUpdate"
    pod_id: str = ""
    location: str = ""
    status: PodStatus = PodStatus.IDLE
    capacity_used: int = 0
    capacity_total: int = 10
    weight_used: float = 0.0
    weight_total: float = 500.0
    battery_level: float = 1.0
    current_route: List[str] = field(default_factory=list)


@dataclass
class PodDecision(Event):
    event_type: str = "PodDecision"
    pod_id: str = ""
    decision_type: str = ""
    decision: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    confidence: float = 0.0
    gemini_response_id: Optional[str] = None
    fallback_used: bool = False


@dataclass
class CongestionAlert(Event):
    event_type: str = "CongestionAlert"
    station_id: str = ""
    congestion_level: float = 0.0  # 0.0-1.0
    queue_length: int = 0
    average_wait_time: float = 0.0
    affected_routes: List[str] = field(default_factory=list)
    estimated_clear_time: Optional[datetime] = None
    severity: str = "low"


@dataclass
class SystemSnapshot(Event):
    event_type: str = "SystemSnapshot"
    snapshot_id: str = field(
        default_factory=lambda: f"snap_{datetime.now(datetime.UTC).strftime('%Y%m%d_%H%M%S')}")
    system_state: Dict[str, Any] = field(default_factory=dict)


# Command Events
@dataclass
class Command(Event):
    command_id: str = field(default_factory=lambda: str(uuid4()))
    command_type: str = ""
    target: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssignRoute(Command):
    command_type: str = "AssignRoute"
    target_pod: str = ""
    route: List[str] = field(default_factory=list)
    priority: int = Priority.NORMAL.value
    deadline: Optional[datetime] = None


@dataclass
class UpdateCapacity(Command):
    command_type: str = "UpdateCapacity"
    target_station: str = ""
    max_pods: int = 0
    processing_rate: float = 0.0


# Data Models
@dataclass
class Passenger:
    passenger_id: str
    origin: str
    destination: str
    priority: Priority
    group_size: int = 1
    special_needs: List[str] = field(default_factory=list)
    arrival_time: datetime = field(default_factory=datetime.utcnow)
    wait_time_limit: int = 30
    pickup_time: Optional[datetime] = None
    delivery_time: Optional[datetime] = None
    assigned_pod: Optional[str] = None


@dataclass
class Cargo:
    request_id: str
    origin: str
    destination: str
    weight: float
    volume: float
    priority: Priority
    hazardous: bool = False
    temperature_controlled: bool = False
    deadline: Optional[datetime] = None
    arrival_time: datetime = field(default_factory=datetime.utcnow)
    load_time: Optional[datetime] = None
    delivery_time: Optional[datetime] = None
    assigned_pod: Optional[str] = None


@dataclass
class Route:
    route_id: str
    stations: List[str]
    estimated_duration: int = 0  # minutes
    distance: float = 0.0
    traffic_level: float = 0.0  # 0.0-1.0
    congestion_factor: float = 1.0


@dataclass
class DecisionContext:
    pod_id: str
    current_location: str
    current_route: List[str]
    capacity_available: int
    weight_available: float
    battery_level: float
    available_requests: List[Dict[str, Any]]
    network_state: Dict[str, Any]
    system_metrics: Dict[str, Any]


@dataclass
class Decision:
    decision_type: str
    accepted_requests: List[str]
    rejected_requests: List[str]
    route: List[str]
    estimated_duration: int
    confidence: float
    reasoning: str
    fallback_used: bool = False


@dataclass
class DecisionOutcome:
    decision_id: str
    actual_duration: int
    efficiency_score: float
    passenger_satisfaction: float
    cargo_on_time_rate: float
    lessons_learned: List[str] = field(default_factory=list)
