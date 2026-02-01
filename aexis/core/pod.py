import logging
import sys
from collections import deque
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Dict, Optional, Any, Deque

from .message_bus import EventProcessor, MessageBus
from .model import (
    Decision,
    DecisionContext,
    LocationDescriptor,
    PodDecision,
    PodPositionUpdate,
    PodStatus,
    PodStatusUpdate,
    Route,
    Coordinate,
    EdgeSegment,
)
from .routing import OfflineRouter, RoutingProvider

logging.basicConfig(
    level=logging.WARN,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("aexis_core.pod.log"),
    ],
)
logger = logging.getLogger(__name__)


class PodType(Enum):
    """Enumeration of pod types for system identification"""
    PASSENGER = "passenger"
    CARGO = "cargo"


class Pod(EventProcessor):
    """Base Autonomous pod class"""

    def __init__(
        self,
        message_bus: MessageBus,
        pod_id: str,
        routing_provider: RoutingProvider | None = None,
    ):
        """Initialize pod with dependency injection (DIP compliant)

        Args:
            message_bus: Message bus for event publishing
            pod_id: Pod identifier
            routing_provider: Routing provider for route decisions. Pod is agnostic to routing implementation.
                            If None, creates default provider with offline routing.
        """
        super().__init__(message_bus, pod_id)
        self.pod_id = pod_id
        self.status = PodStatus.IDLE

        # PHASE 1: Position tracking on network
        self.location_descriptor = LocationDescriptor(
            "station", "station_001")  # Default
        
        # Continuous Navigation State
        self.route_queue: Deque[EdgeSegment] = deque()
        self.current_segment: Optional[EdgeSegment] = None
        self.segment_progress: float = 0.0  # Meters traveled on current segment
        self.speed: float = 20.0  # Increased speed for better responsiveness (m/s)

        self.current_route: Route | None = None
        self.movement_start_time = None
        self.estimated_arrival = None

        # Pod type identification (to be set by subclasses)
        self.pod_type = self._get_pod_type()

        # Setup routing provider (DIP compliant, implementation-agnostic)
        if routing_provider:
            # Use injected provider (for testing or external configuration)
            self.routing_provider = routing_provider
        else:
            # Create default provider with offline routing
            self.routing_provider = RoutingProvider()
            self.routing_provider.add_router(OfflineRouter())

    def _get_pod_type(self) -> PodType:
        """Get the pod type - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement _get_pod_type")

    def get_pod_constraints(self) -> Dict[str, Any]:
        """Get pod-specific constraints for routing decisions"""
        cap_used, cap_total, w_used, w_total = self._get_capacity_status()
        return {
            "pod_type": self.pod_type.value,
            "capacity_available": cap_total - cap_used,
            "weight_available": w_total - w_used,
            "max_capacity": cap_total,
            "max_weight": w_total,
            "current_load": {
                "passengers": cap_used,
                "cargo_weight": w_used
            }
        }

    async def _setup_subscriptions(self):
        """Subscribe to relevant channels"""
        self.message_bus.subscribe(
            MessageBus.CHANNELS["POD_COMMANDS"], self._handle_command
        )
        self.message_bus.subscribe(
            MessageBus.CHANNELS["SYSTEM_EVENTS"], self._handle_system_event
        )

    async def _cleanup_subscriptions(self):
        """Unsubscribe from channels"""
        self.message_bus.unsubscribe(
            MessageBus.CHANNELS["POD_COMMANDS"], self._handle_command
        )
        self.message_bus.unsubscribe(
            MessageBus.CHANNELS["SYSTEM_EVENTS"], self._handle_system_event
        )

    async def _handle_command(self, data: dict):
        """Handle incoming commands"""
        try:
            command_type = data.get("message", {}).get("command_type", "")
            target = data.get("message", {}).get("target", "")

            if target != self.pod_id:
                return

            if command_type == "AssignRoute":
                await self._handle_route_assignment(data)

        except KeyError as e:
            logger.warning(
                f"Pod {self.pod_id}: malformed command message - missing key {e}"
            )
        except Exception as e:
            logger.error(
                f"Pod {self.pod_id} command handling error: {e}", exc_info=True
            )

    async def _handle_system_event(self, data: dict):
        """Handle system-wide events"""
        try:
            event_type = data.get("message", {}).get("event_type", "")

            # React to congestion alerts
            if event_type == "CongestionAlert":
                await self._handle_congestion_alert(data)

        except KeyError as e:
            logger.warning(
                f"Pod {self.pod_id}: malformed event data - missing key {e}")
        except Exception as e:
            logger.error(
                f"Pod {self.pod_id} event handling error: {e}", exc_info=True)

    async def _handle_route_assignment(self, data: dict):
        """Handle route assignment command"""
        try:
            parameters = data.get("message", {}).get("parameters", {})
            # Expecting list of stations or Route dict
            route_data = parameters.get("route", [])

            # Handle if route is just list of strings (legacy/command input)
            # We need to convert it to a Route object
            # For MVP, if we get a list, we wrap it in a dummy Route
            if isinstance(route_data, list):
                from .model import Route

                # Simple dummy route object
                route_obj = Route(
                    route_id=f"route_{datetime.now().timestamp()}",
                    stations=route_data,
                    estimated_duration=len(route_data) * 5,
                )
                self.current_route = route_obj
            elif isinstance(route_data, dict):
                # Deserialize from dict with validation
                required_fields = {"route_id",
                                   "stations", "estimated_duration"}
                if not required_fields.issubset(route_data.keys()):
                    logger.error(
                        f"Invalid route object: missing fields {required_fields - route_data.keys()}"
                    )
                    return
                route_obj = Route(
                    route_id=route_data["route_id"],
                    stations=route_data["stations"],
                    estimated_duration=route_data["estimated_duration"],
                )
                self.current_route = route_obj
            else:
                logger.error(
                    f"Invalid route data type: {type(route_data)}. Expected list or dict."
                )
                return

            if self.current_route and self.current_route.stations:
                # Hydrate route into edge segments
                await self._hydrate_route(self.current_route.stations)
                
                self.status = PodStatus.EN_ROUTE
                self.movement_start_time = datetime.now(UTC)
                self.estimated_arrival = self.movement_start_time + timedelta(
                    minutes=self.current_route.estimated_duration
                )

                await self._publish_status_update()
                logger.info(
                    f"Pod {self.pod_id} assigned route: {self.current_route.stations}"
                )

        except ValueError as e:
            logger.error(f"Pod {self.pod_id}: invalid route data - {e}")
        except Exception as e:
            logger.error(
                f"Pod {self.pod_id} route assignment error: {e}", exc_info=True
            )

    async def _hydrate_route(self, stations: list[str]):
        """Convert list of station IDs into a queue of EdgeSegments for navigation"""
        from .network import NetworkContext
        network = NetworkContext.get_instance()
        
        self.route_queue.clear()
        self.current_segment = None
        self.segment_progress = 0.0
        
        if len(stations) < 2:
            return

        for i in range(len(stations) - 1):
            start = stations[i]
            end = stations[i+1]
            edge_id = f"{start}->{end}"
            
            # Check edge existence
            if edge_id in network.edges:
                self.route_queue.append(network.edges[edge_id])
            else:
                # Fallback: Create synthetic edge if missing from map (robustness)
                logger.warning(f"Pod {self.pod_id} hydrating synthetic edge {edge_id}")
                p1 = network.station_positions.get(start, (0,0))
                p2 = network.station_positions.get(end, (0,0))
                synthetic_edge = EdgeSegment(
                    segment_id=edge_id,
                    start_node=start,
                    end_node=end,
                    start_coord=Coordinate(p1[0], p1[1]),
                    end_coord=Coordinate(p2[0], p2[1])
                )
                self.route_queue.append(synthetic_edge)
        
        # Prime the first segment
        if self.route_queue:
            self.current_segment = self.route_queue.popleft()
            self.segment_progress = 0.0

    async def _handle_congestion_alert(self, data: dict):
        """Handle congestion alerts"""
        try:
            alert_data = data.get("message", {}).get("data", {})
            affected_routes = alert_data.get("affected_routes", [])

            if not self.current_route or not self.current_route.stations:
                return

            # Check if current route is affected
            current_route_str = "->".join(self.current_route.stations)
            if any(route in current_route_str for route in affected_routes):
                logger.info(f"Pod {self.pod_id} route affected by congestion")
                # Could trigger re-routing decision here

        except KeyError as e:
            logger.warning(
                f"Pod {self.pod_id}: malformed congestion alert - missing key {e}"
            )
        except Exception as e:
            logger.error(
                f"Pod {self.pod_id} congestion handling error: {e}", exc_info=True
            )

    async def make_decision(self):
        """Make routing decision (async to handle routing provider)"""
        try:
            # Build decision context
            context = await self._build_decision_context()

            # Get route from routing provider (now properly async)
            route = await self.routing_provider.route(context)

            # Convert route to decision format
            decision = Decision(
                decision_type="route_selection",
                accepted_requests=[],
                rejected_requests=[],
                route=route.stations,
                estimated_duration=route.estimated_duration,
                confidence=0.8,
                reasoning="Route determined by RoutingProvider",
                fallback_used=False,
            )

            # Execute decision
            await self._execute_decision(decision)

            # Publish decision event
            await self._publish_decision_event(decision)

        except ValueError as e:
            logger.error(
                f"Pod {self.pod_id}: routing failure (all strategies exhausted) - {e}"
            )
        except Exception as e:
            logger.error(
                f"Pod {self.pod_id} decision making error: {e}", exc_info=True)

    async def _build_decision_context(self) -> DecisionContext:
        """Build context for decision making - must be implemented by subclasses

        Subclasses MUST override this method to provide pod-specific context.
        Base Pod class should never be instantiated directly.

        Raises:
            NotImplementedError: Always. This method must be overridden.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _build_decision_context(). "
            "Pod is an abstract class and should not be instantiated directly."
        )

    async def _execute_decision(self, decision: Decision):
        """Execute the routing decision"""
        if decision.route:
            # Create Route object from decision data
            from .model import Route

            self.current_route = Route(
                route_id=f"rt_{datetime.now().timestamp()}",
                stations=decision.route,
                estimated_duration=decision.estimated_duration,
            )

            self.status = PodStatus.EN_ROUTE
            self.movement_start_time = datetime.now(UTC)

            logger.info(
                f"Pod {self.pod_id} executing decision: {decision.route}")

        # Logic to "load" passengers/cargo based on accepted requests would go here
        # For MVP we just track them in the list

    async def _publish_decision_event(self, decision: Decision):
        """Publish pod decision event"""
        event = PodDecision(
            pod_id=self.pod_id,
            decision_type=decision.decision_type,
            decision={
                "accepted_requests": decision.accepted_requests,
                "rejected_requests": decision.rejected_requests,
                "route": decision.route,
                "estimated_duration": decision.estimated_duration,
                "confidence": decision.confidence,
            },
            reasoning=decision.reasoning,
            confidence=decision.confidence,
            fallback_used=decision.fallback_used,
        )

        await self.publish_event(event)

    async def _publish_status_update(self):
        """Publish pod status update"""
        # Populate generic fields based on subclass
        cap_used, cap_total, w_used, w_total = self._get_capacity_status()

        event = PodStatusUpdate(
            pod_id=self.pod_id,
            location=self.location_descriptor.node_id if self.location_descriptor.location_type == "station" else self.current_edge,
            status=self.status,
            capacity_used=cap_used,
            capacity_total=cap_total,
            weight_used=w_used,
            weight_total=w_total,
            current_route=self.current_route,
        )

        await self.publish_event(event)

    # ========================================================================
    # PHASE 1: Movement Simulation on Network Edges
    # ========================================================================

    # ========================================================================
    # PHASE 1: Movement Simulation on Network Edges
    # ========================================================================

    async def update(self, dt: float) -> bool:
        """Update pod physics for time step dt
        
        Implements Continuous Path Integration:
        - Consumes distance from current segment
        - Overflows to next segment in queue if dt > remaining length
        - Handles precise position interpolation
        """
        if self.status != PodStatus.EN_ROUTE or not self.current_segment:
            return False

        dist_to_travel = self.speed * dt
        # Safety cap to prevent warping across map in one lag spike (e.g. max 100m/tick)
        dist_to_travel = min(dist_to_travel, 100.0) 

        while dist_to_travel > 0:
            if not self.current_segment:
                # End of route reached
                await self._handle_route_completion()
                return True

            remaining_on_edge = self.current_segment.length - self.segment_progress
            
            if dist_to_travel >= remaining_on_edge:
                # Overflow case: Complete this edge and continue to next
                dist_to_travel -= remaining_on_edge
                self._advance_segment()
            else:
                # Normal case: Move along current edge
                self.segment_progress += dist_to_travel
                dist_to_travel = 0
        
        # Update observable location state
        self._update_location_descriptor()
        
        # Publish exactly one position update per physics tick
        # This gives the UI the final resolved position after all internal edge transitions
        await self._publish_position_update()
        return False

    def _advance_segment(self):
        """Move to next segment in queue"""
        if self.route_queue:
            self.current_segment = self.route_queue.popleft()
            self.segment_progress = 0.0
        else:
            # No more segments, we have arrived at final destination node of the last segment
            # Mark as finished so next loop iteration catches it
            self.current_segment = None

    def _update_location_descriptor(self):
        """Update the public location descriptor based on internal physics state"""
        if not self.current_segment:
            return

        # Interpolate exact position
        current_coord = self.current_segment.get_point_at_distance(self.segment_progress)
        
        self.location_descriptor = LocationDescriptor(
            location_type="edge",
            edge_id=self.current_segment.segment_id,
            coordinate=current_coord,
            distance_on_edge=self.segment_progress
        )

    async def _handle_route_completion(self):
        """Handle arrival at destination"""
        self.status = PodStatus.IDLE
        self.segment_progress = 0.0
        
        # Snap to final station coordinate
        if self.current_route and self.current_route.stations:
            final_station = self.current_route.stations[-1]
            from .network import NetworkContext
            nc = NetworkContext.get_instance()
            pos = nc.station_positions.get(final_station, (0,0))
            
            self.location_descriptor = LocationDescriptor(
                location_type="station",
                node_id=final_station,
                coordinate=Coordinate(pos[0], pos[1])
            )
        
        await self._publish_position_update()
        await self._publish_status_update()
        logger.info(f"Pod {self.pod_id} arrived at destination")

    async def navigate_to_station(self, target_station: str) -> bool:
        """Start navigation from current position to target station

        Args:
            target_station: Station ID to navigate to

        Returns:
            True if navigation started, False if already at station
        """
        try:
            from .network import NetworkContext
            import networkx as nx

            network = NetworkContext.get_instance()

            # If already at a station, find path from there
            if self.location_descriptor.location_type == "station":
                current_station = self.location_descriptor.node_id
            else:
                # On an edge - find nearest station or endpoint
                current_station = network.get_nearest_station(
                    self.location_descriptor.coordinate)

            if current_station == target_station:
                logger.debug(f"Pod {self.pod_id} already at {target_station}")
                return False

            # Find shortest path using network graph
            try:
                path = nx.shortest_path(
                    network.network_graph, current_station, target_station)
                if len(path) < 2:
                    return False

                # Start navigation using new system
                # Convert path to segments
                # Since we are already in async method, we can hydrate immediately
                
                # Create a mock route object for hydration
                dummy_route = Route(
                    route_id=f"nav_{datetime.now().timestamp()}",
                    stations=path,
                    estimated_duration=10 # Estimation...
                )
                self.current_route = dummy_route
                
                # Hydrate
                await self._hydrate_route(path)
                
                if self.current_segment:
                    self.status = PodStatus.EN_ROUTE
                    logger.info(
                        f"Pod {self.pod_id} starting navigation to {target_station}")
                    return True
                return False

                return False
            except nx.NetworkXNoPath:
                logger.warning(
                    f"Pod {self.pod_id}: no path to {target_station}")
                return False

        except Exception as e:
            logger.error(
                f"Pod {self.pod_id} navigation error: {e}", exc_info=True)
            return False

    async def _publish_position_update(self):
        """Publish real-time position update for UI streaming"""
        event = PodPositionUpdate(
            pod_id=self.pod_id,
            location=self.location_descriptor,
            status=self.status.value,
            current_route=self.current_route.stations if self.current_route else None
        )
        await self.publish_event(event)

    def _get_capacity_status(self):
        """Return (cap_used, cap_total, weight_used, weight_total)"""
        return 0, 0, 0.0, 0.0

    def get_state(self) -> dict:
        """Get current pod state"""
        cap_used, cap_total, w_used, w_total = self._get_capacity_status()

        # Build location description
        if self.location_descriptor.location_type == "station":
            location_str = self.location_descriptor.node_id
        else:
            location_str = f"on edge {self.location_descriptor.edge_id} @ {self.distance_on_edge:.1f}m"

        return {
            "pod_id": self.pod_id,
            "pod_type": self._get_pod_type().value,
            "type": self.__class__.__name__,
            "status": self.status.value,
            "location": location_str,
            "coordinate": {"x": self.location_descriptor.coordinate.x, "y": self.location_descriptor.coordinate.y},
            "capacity": {"used": cap_used, "total": cap_total},
            "weight": {"used": w_used, "total": w_total},
            "current_route": [s for s in self.current_route.stations]
            if self.current_route
            else [],
            "estimated_arrival": self.estimated_arrival.isoformat()
            if self.estimated_arrival
            else None,
        }


class PassengerPod(Pod):
    """Pod specialized for passenger transport"""

    def __init__(
        self,
        message_bus: MessageBus,
        pod_id: str,
        routing_provider: RoutingProvider | None = None,
    ):
        super().__init__(message_bus, pod_id, routing_provider)
        self.capacity = 4  # Seats
        self.passengers = []  # List[str] IDs

    def _get_pod_type(self) -> PodType:
        """Return passenger pod type"""
        return PodType.PASSENGER

    async def _build_decision_context(self) -> DecisionContext:
        """Build decision context with passenger-specific constraints"""
        constraints = self.get_pod_constraints()

        # Get current location - either station or nearest station if on edge
        if self.location_descriptor.location_type == "station":
            current_location = self.location_descriptor.node_id
        else:
            from .network import NetworkContext
            network = NetworkContext.get_instance()
            current_location = network.get_nearest_station(
                self.location_descriptor.coordinate)

        return DecisionContext(
            pod_id=self.pod_id,
            current_location=current_location,
            current_route=self.current_route,
            capacity_available=self.capacity - len(self.passengers),
            weight_available=0.0,  # Passenger pods don't handle weight
            available_requests=[],  # To be filled by system
            network_state={},
            system_metrics={},
            # Enhanced context with pod type information
            pod_type=self.pod_type.value,
            pod_constraints=constraints,
            specialization="passenger_transport"
        )

    def _get_capacity_status(self):
        return len(self.passengers), self.capacity, 0.0, 0.0

    def get_state(self) -> dict:
        state = super().get_state()
        state["passengers"] = self.passengers
        return state


class CargoPod(Pod):
    """Pod specialized for cargo transport"""

    def __init__(
        self,
        message_bus: MessageBus,
        pod_id: str,
        routing_provider: RoutingProvider | None = None,
    ):
        super().__init__(message_bus, pod_id, routing_provider)
        self.weight_capacity = 500.0  # kg
        self.current_weight = 0.0
        self.cargo = []  # List[str] IDs

    def _get_pod_type(self) -> PodType:
        """Return cargo pod type"""
        return PodType.CARGO

    async def _build_decision_context(self) -> DecisionContext:
        """Build decision context with cargo-specific constraints"""
        constraints = self.get_pod_constraints()

        # Get current location - either station or nearest station if on edge
        if self.location_descriptor.location_type == "station":
            current_location = self.location_descriptor.node_id
        else:
            from .network import NetworkContext
            network = NetworkContext.get_instance()
            current_location = network.get_nearest_station(
                self.location_descriptor.coordinate)

        return DecisionContext(
            pod_id=self.pod_id,
            current_location=current_location,
            current_route=self.current_route,
            capacity_available=0,  # Cargo pods don't handle passenger capacity
            weight_available=self.weight_capacity - self.current_weight,
            available_requests=[],  # To be filled by system
            network_state={},
            system_metrics={},
            # Enhanced context with pod type information
            pod_type=self.pod_type.value,
            pod_constraints=constraints,
            specialization="cargo_transport"
        )

    def _get_capacity_status(self):
        return 0, 0, self.current_weight, self.weight_capacity

    def get_state(self) -> dict:
        state = super().get_state()
        state["cargo"] = self.cargo
        return state
