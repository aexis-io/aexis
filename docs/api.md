# API Reference

## Core Events

### Event Schema Definition

All events follow this base structure:
```json
{
  "event_id": "uuid-v4",
  "event_type": "EventType",
  "timestamp": "2024-01-15T10:30:00.123Z",
  "source": "component_id",
  "data": { /* event-specific data */ }
}
```

### Passenger Events

#### PassengerArrival
```json
{
  "event_type": "PassengerArrival",
  "data": {
    "passenger_id": "p_12345",
    "station_id": "station_001",
    "destination": "station_005",
    "priority": 3,
    "group_size": 2,
    "special_needs": ["wheelchair"],
    "wait_time_limit": 15
  }
}
```

#### PassengerPickedUp
```json
{
  "event_type": "PassengerPickedUp",
  "data": {
    "passenger_id": "p_12345",
    "pod_id": "pod_007",
    "station_id": "station_001",
    "pickup_time": "2024-01-15T10:32:00.123Z"
  }
}
```

#### PassengerDelivered
```json
{
  "event_type": "PassengerDelivered",
  "data": {
    "passenger_id": "p_12345",
    "pod_id": "pod_007",
    "station_id": "station_005",
    "delivery_time": "2024-01-15T10:45:00.123Z",
    "total_travel_time": 780,
    "satisfaction_score": 4.5
  }
}
```

### Cargo Events

#### CargoRequest
```json
{
  "event_type": "CargoRequest",
  "data": {
    "request_id": "c_67890",
    "origin": "station_002",
    "destination": "station_008",
    "weight": 45.2,
    "volume": 0.12,
    "priority": 4,
    "hazardous": false,
    "temperature_controlled": true,
    "deadline": "2024-01-15T14:00:00.000Z"
  }
}
```

#### CargoLoaded
```json
{
  "event_type": "CargoLoaded",
  "data": {
    "request_id": "c_67890",
    "pod_id": "pod_012",
    "station_id": "station_002",
    "load_time": "2024-01-15T11:15:00.123Z"
  }
}
```

#### CargoDelivered
```json
{
  "event_type": "CargoDelivered",
  "data": {
    "request_id": "c_67890",
    "pod_id": "pod_012",
    "station_id": "station_008",
    "delivery_time": "2024-01-15T12:30:00.123Z",
    "condition": "good",
    "on_time": true
  }
}
```

### Pod Events

#### PodStatusUpdate
```json
{
  "event_type": "PodStatusUpdate",
  "data": {
    "pod_id": "pod_007",
    "location": "station_003",
    "status": "loading",
    "capacity_used": 7,
    "capacity_total": 10,
    "weight_used": 320.5,
    "weight_total": 500.0,
    "battery_level": 0.87,
    "current_route": ["station_003", "station_005", "station_007"]
  }
}
```

#### PodDecision
```json
{
  "event_type": "PodDecision",
  "data": {
    "pod_id": "pod_007",
    "decision_type": "route_selection",
    "decision": {
      "accepted_requests": ["p_12345", "c_67890"],
      "rejected_requests": ["p_54321"],
      "route": ["station_003", "station_001", "station_005"],
      "estimated_duration": 25,
      "confidence": 0.92
    },
    "reasoning": "Optimized for high-priority cargo and passenger satisfaction",
    "gemini_response_id": "gemini_resp_abc123"
  }
}
```

### System Events

#### CongestionAlert
```json
{
  "event_type": "CongestionAlert",
  "data": {
    "station_id": "station_004",
    "congestion_level": 0.78,
    "queue_length": 12,
    "average_wait_time": 8.5,
    "affected_routes": ["station_004->station_005", "station_004->station_006"],
    "estimated_clear_time": "2024-01-15T11:00:00.000Z"
  }
}
```

#### SystemSnapshot
```json
{
  "event_type": "SystemSnapshot",
  "data": {
    "snapshot_id": "snap_20240115_103000",
    "timestamp": "2024-01-15T10:30:00.000Z",
    "system_state": {
      "total_pods": 25,
      "active_pods": 23,
      "total_stations": 8,
      "pending_passengers": 34,
      "pending_cargo": 18,
      "average_wait_time": 4.2,
      "system_efficiency": 0.84
    }
  }
}
```

## Message Bus API

### Redis Channels

#### Event Channels
```
aexis:events:passenger     # Passenger lifecycle events
aexis:events:cargo         # Cargo lifecycle events  
aexis:events:pods          # Pod status and decisions
aexis:events:system        # System-wide events
aexis:events:congestion    # Congestion alerts
```

#### Command Channels
```
aexis:commands:pods        # Pod control commands
aexis:commands:stations     # Station control commands
aexis:commands:system       # System control commands
```

### Message Format

#### Publish Request
```json
{
  "channel": "aexis:events:passenger",
  "message": {
    "event_id": "uuid-v4",
    "event_type": "PassengerArrival",
    "timestamp": "2024-01-15T10:30:00.123Z",
    "source": "station_001",
    "data": {
      "passenger_id": "p_12345",
      "station_id": "station_001",
      "destination": "station_005",
      "priority": 3,
      "group_size": 2
    }
  }
}
```

#### Subscribe Response
```json
{
  "channel": "aexis:events:passenger",
  "message": {
    "event_id": "uuid-v4",
    "event_type": "PassengerArrival",
    "timestamp": "2024-01-15T10:30:00.123Z",
    "source": "station_001",
    "data": {
      "passenger_id": "p_12345",
      "station_id": "station_001",
      "destination": "station_005",
      "priority": 3,
      "group_size": 2
    }
  }
}
```

### Command Messages

#### Pod Route Assignment
```json
{
  "channel": "aexis:commands:pods",
  "message": {
    "command_id": "cmd_45678",
    "command_type": "AssignRoute",
    "target_pod": "pod_007",
    "timestamp": "2024-01-15T10:35:00.000Z",
    "parameters": {
      "route": ["station_003", "station_001", "station_005"],
      "priority": 4,
      "deadline": "2024-01-15T11:00:00.000Z"
    }
  }
}
```

#### Station Capacity Update
```json
{
  "channel": "aexis:commands:stations",
  "message": {
    "command_id": "cmd_45679",
    "command_type": "UpdateCapacity",
    "target_station": "station_004",
    "timestamp": "2024-01-15T10:40:00.000Z",
    "parameters": {
      "max_pods": 5,
      "processing_rate": 2.5
    }
  }
}
```

## Core Classes

### MessageBus

```python
class MessageBus:
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.pubsub = redis.pubsub()
    
    def publish(self, channel: str, event: Event) -> None:
        """Publish event to Redis channel"""
        
    def subscribe(self, channel: str, handler: Callable) -> None:
        """Subscribe to channel with event handler"""
        
    def start_listening(self) -> None:
        """Start listening for subscribed events"""
```

### Pod

```python
class Pod:
    def __init__(self, pod_id: str, gemini_client: genai.Client):
        self.id = pod_id
        self.gemini = gemini_client
        self.thought_signature = None
        self.location = None
        self.capacity = 10
        self.current_load = 0
    
    async def handle_event(self, event: Event) -> None:
        """Handle incoming event and make decisions"""
        
    def make_decision(self, context: DecisionContext) -> Decision:
        """Use Gemini 3 to make routing decision"""
        
    def execute_decision(self, decision: Decision) -> None:
        """Execute the decided action"""
```

### Station

```python
class Station:
    def __init__(self, station_id: str, message_bus: MessageBus):
        self.id = station_id
        self.message_bus = message_bus
        self.passenger_queue = []
        self.cargo_queue = []
        self.connected_stations = []
    
    def handle_passenger_arrival(self, event: PassengerArrival) -> None:
        """Process new passenger arrival"""
        
    def handle_cargo_request(self, event: CargoRequest) -> None:
        """Process new cargo request"""
        
    def calculate_congestion(self) -> float:
        """Calculate current congestion level"""
```

## Gemini 3 Integration

### Decision Prompts

#### Route Optimization
```python
def build_routing_prompt(self, context: DecisionContext) -> str:
    return f"""
    As Pod {self.id}, analyze this transportation scenario:
    
    Current State:
    - Location: {self.location}
    - Capacity: {self.capacity - self.current_load}/{self.capacity}
    - Current load: {self.current_passengers} passengers, {self.current_cargo} kg cargo
    
    Available Requests:
    {format_requests(context.available_requests)}
    
    Network Conditions:
    {format_network_conditions(context.network_state)}
    
    Decision Required:
    1. Which requests should I accept?
    2. What route should I take?
    3. What are the trade-offs?
    
    Consider:
    - Passenger priorities
    - Cargo urgency
    - Traffic congestion
    - Capacity constraints
    - Overall system efficiency
    """
```

### Thought Signatures

```python
def update_thought_signature(self, decision: Decision, outcome: DecisionOutcome) -> None:
    """Update persistent thought signature based on decision outcomes"""
    
    reflection = f"""
    Previous Decision: {decision.summary}
    Actual Outcome: {outcome.summary}
    Efficiency: {outcome.efficiency_score}
    Lessons Learned: {self.extract_lessons(decision, outcome)}
    """
    
    self.thought_signature = self.gemini.models.generate_content(
        model="gemini-3-pro-preview",
        contents=f"Update thought signature with: {reflection}",
        # Use previous signature for continuity
    )
```

## Web API

### REST Endpoints

#### System Status
```http
GET /api/status
Content-Type: application/json
```

**Response:**
```json
{
  "system_state": "running",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "metrics": {
    "active_pods": 23,
    "total_pods": 25,
    "total_stations": 8,
    "pending_requests": {
      "passengers": 34,
      "cargo": 18
    },
    "performance": {
      "average_wait_time": 4.2,
      "throughput_per_hour": 145,
      "system_efficiency": 0.84
    }
  }
}
```

#### Pod Information
```http
GET /api/pods/{pod_id}
Content-Type: application/json
```

**Response:**
```json
{
  "pod_id": "pod_007",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "status": {
    "location": "station_003",
    "state": "loading",
    "battery_level": 0.87
  },
  "capacity": {
    "passengers": {
      "current": 7,
      "total": 10
    },
    "cargo": {
      "current_weight": 320.5,
      "max_weight": 500.0
    }
  },
  "route": {
    "current": ["station_003", "station_001", "station_005"],
    "estimated_arrival": "2024-01-15T10:45:00.000Z",
    "progress": 0.3
  },
  "last_decision": {
    "timestamp": "2024-01-15T10:25:00.000Z",
    "type": "route_selection",
    "reasoning": "Optimized for high-priority cargo and passenger satisfaction",
    "confidence": 0.92,
    "gemini_response_id": "gemini_resp_abc123"
  }
}
```

#### Station Information
```http
GET /api/stations/{station_id}
Content-Type: application/json
```

**Response:**
```json
{
  "station_id": "station_003",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "status": {
    "congestion_level": 0.65,
    "operational": true
  },
  "queues": {
    "passengers": {
      "waiting": 12,
      "average_wait_time": 4.1,
      "max_wait_time": 15.2
    },
    "cargo": {
      "waiting": 5,
      "average_wait_time": 6.8,
      "max_wait_time": 22.1
    }
  },
  "resources": {
    "loading_bays": {
      "available": 2,
      "total": 4
    },
    "processing_rate": 2.5
  },
  "connected_pods": 3,
  "recent_arrivals": [
    {
      "type": "passenger",
      "count": 2,
      "timestamp": "2024-01-15T10:28:00.000Z"
    }
  ]
}
```

#### Create Passenger Request
```http
POST /api/passengers
Content-Type: application/json

{
  "station_id": "station_001",
  "destination": "station_005",
  "priority": 3,
  "group_size": 2,
  "special_needs": ["wheelchair"]
}
```

**Response:**
```json
{
  "passenger_id": "p_12345",
  "request_status": "queued",
  "estimated_wait_time": 4.2,
  "queue_position": 3,
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

#### Create Cargo Request
```http
POST /api/cargo
Content-Type: application/json

{
  "origin": "station_002",
  "destination": "station_008",
  "weight": 45.2,
  "volume": 0.12,
  "priority": 4,
  "hazardous": false,
  "temperature_controlled": true,
  "deadline": "2024-01-15T14:00:00.000Z"
}
```

**Response:**
```json
{
  "request_id": "c_67890",
  "request_status": "queued",
  "estimated_pickup_time": "2024-01-15T11:15:00.000Z",
  "estimated_delivery_time": "2024-01-15T12:30:00.000Z",
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

#### System Metrics
```http
GET /api/metrics?period=1h&granularity=5m
Content-Type: application/json
```

**Response:**
```json
{
  "period": "1h",
  "granularity": "5m",
  "metrics": [
    {
      "timestamp": "2024-01-15T09:30:00.000Z",
      "throughput": {
        "passengers_delivered": 12,
        "cargo_delivered": 8
      },
      "performance": {
        "average_wait_time": 3.8,
        "system_efficiency": 0.87,
        "pod_utilization": 0.92
      },
      "congestion": {
        "average_level": 0.45,
        "affected_stations": 2
      }
    }
  ]
}
```

### WebSocket Events

#### Connection
```javascript
// Connect to WebSocket
const ws = new WebSocket('ws://localhost:8000/ws');

// Authentication (if required)
ws.send(JSON.stringify({
  type: 'auth',
  token: 'your_api_token'
}));
```

#### Real-time Event Stream

**Pod Decision Event:**
```json
{
  "type": "pod_decision",
  "timestamp": "2024-01-15T10:30:00.123Z",
  "data": {
    "pod_id": "pod_007",
    "decision_type": "route_selection",
    "decision": {
      "accepted_requests": ["p_12345", "c_67890"],
      "rejected_requests": ["p_54321"],
      "route": ["station_003", "station_001", "station_005"],
      "estimated_duration": 25,
      "confidence": 0.92
    },
    "reasoning": "Optimized for high-priority cargo and passenger satisfaction",
    "gemini_response_id": "gemini_resp_abc123"
  }
}
```

**Passenger Arrival Event:**
```json
{
  "type": "passenger_arrival",
  "timestamp": "2024-01-15T10:30:00.123Z",
  "data": {
    "passenger_id": "p_12345",
    "station_id": "station_001",
    "destination": "station_005",
    "priority": 3,
    "group_size": 2,
    "special_needs": ["wheelchair"],
    "estimated_wait_time": 4.2
  }
}
```

**Congestion Alert Event:**
```json
{
  "type": "congestion_alert",
  "timestamp": "2024-01-15T10:30:00.123Z",
  "data": {
    "station_id": "station_004",
    "congestion_level": 0.78,
    "queue_length": 12,
    "average_wait_time": 8.5,
    "affected_routes": ["station_004->station_005", "station_004->station_006"],
    "estimated_clear_time": "2024-01-15T11:00:00.000Z",
    "severity": "high"
  }
}
```

**System Metrics Update:**
```json
{
  "type": "metrics_update",
  "timestamp": "2024-01-15T10:30:00.123Z",
  "data": {
    "system_performance": {
      "throughput_per_hour": 145,
      "average_wait_time": 4.2,
      "system_efficiency": 0.84,
      "pod_utilization": 0.92
    },
    "queues": {
      "total_passengers_waiting": 34,
      "total_cargo_waiting": 18,
      "average_queue_length": 6.5
    }
  }
}
```

#### Client-Side Handling
```javascript
// Event handling
ws.onmessage = function(event) {
    const message = JSON.parse(event.data);
    
    switch(message.type) {
        case 'pod_decision':
            updatePodDisplay(message.data.pod_id, message.data.decision);
            highlightRoute(message.data.decision.route);
            break;
            
        case 'passenger_arrival':
            addPassengerToQueue(message.data);
            updateStationDisplay(message.data.station_id);
            break;
            
        case 'congestion_alert':
            highlightCongestion(message.data.station_id, message.data.congestion_level);
            showNotification(`Congestion at ${message.data.station_id}`, 'warning');
            break;
            
        case 'metrics_update':
            updateDashboard(message.data.system_performance);
            updateQueueDisplays(message.data.queues);
            break;
    }
};

// Error handling
ws.onerror = function(error) {
    console.error('WebSocket error:', error);
    showNotification('Connection lost', 'error');
};

// Reconnection logic
ws.onclose = function() {
    setTimeout(() => {
        console.log('Attempting to reconnect...');
        connectWebSocket();
    }, 5000);
};
```

#### Subscription Management
```javascript
// Subscribe to specific events
ws.send(JSON.stringify({
  type: 'subscribe',
  events: ['pod_decision', 'congestion_alert', 'passenger_arrival'],
  filters: {
    station_ids: ['station_001', 'station_003'],
    pod_ids: ['pod_007']
  }
}));

// Unsubscribe from events
ws.send(JSON.stringify({
  type: 'unsubscribe',
  events: ['system_metrics']
}));
```

## Configuration

### Environment Variables
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- `GEMINI_API_KEY`, `GEMINI_MODEL`
- `POD_COUNT`, `STATION_COUNT`
- `UI_PORT`, `LOG_LEVEL`

### System Parameters
- Pod capacity limits
- Station processing rates
- Decision timeout values
- Event retention periods
