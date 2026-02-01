import logging
import sys
from datetime import UTC, datetime, timedelta

from .message_bus import EventProcessor, MessageBus
from .model import (
    Decision,
    DecisionContext,
    PodDecision,
    PodStatus,
    PodStatusUpdate,
    Route,
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
        self.location = "station_001"

        self.current_route: Route | None = None
        self.movement_start_time = None
        self.estimated_arrival = None

        # Setup routing provider (DIP compliant, implementation-agnostic)
        if routing_provider:
            # Use injected provider (for testing or external configuration)
            self.routing_provider = routing_provider
        else:
            # Build default provider with offline routing
            # Pod doesn't care if routing is AI-based, offline, or hybrid - it's transparent
            self.routing_provider = RoutingProvider()
            self.routing_provider.add_router(OfflineRouter())

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
            logger.warning(f"Pod {self.pod_id}: malformed event data - missing key {e}")
        except Exception as e:
            logger.error(f"Pod {self.pod_id} event handling error: {e}", exc_info=True)

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
                required_fields = {"route_id", "stations", "estimated_duration"}
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

    async def _handle_congestion_alert(self, data: dict):
        """Handle congestion alerts"""
        try:
            alert_data = data.get("message", {}).get("data", {})
            affected_routes = alert_data.get("affected_routes", [])

            if not self.current_route or not self.current_route.stations:
                returnX

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
            logger.error(f"Pod {self.pod_id} decision making error: {e}", exc_info=True)

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

            logger.info(f"Pod {self.pod_id} executing decision: {decision.route}")

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
            location=self.location,
            status=self.status,
            capacity_used=cap_used,
            capacity_total=cap_total,
            weight_used=w_used,
            weight_total=w_total,
            current_route=self.current_route,
        )

        await self.publish_event(event)

    def _get_capacity_status(self):
        """Return (cap_used, cap_total, weight_used, weight_total)"""
        return 0, 0, 0.0, 0.0

    def get_state(self) -> dict:
        """Get current pod state"""
        cap_used, cap_total, w_used, w_total = self._get_capacity_status()
        return {
            "pod_id": self.pod_id,
            "type": self.__class__.__name__,
            "status": self.status.value,
            "location": self.location,
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

    async def _build_decision_context(self) -> DecisionContext:
        return DecisionContext(
            pod_id=self.pod_id,
            current_location=self.location,
            current_route=self.current_route,
            capacity_available=self.capacity - len(self.passengers),
            weight_available=0.0,
            available_requests=[],
            network_state={},
            system_metrics={},
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

    async def _build_decision_context(self) -> DecisionContext:
        return DecisionContext(
            pod_id=self.pod_id,
            current_location=self.location,
            current_route=self.current_route,
            capacity_available=0,
            weight_available=self.weight_capacity - self.current_weight,
            available_requests=[],
            network_state={},
            system_metrics={},
        )

    def _get_capacity_status(self):
        return 0, 0, self.current_weight, self.weight_capacity

    def get_state(self) -> dict:
        state = super().get_state()
        state["cargo"] = self.cargo
        return state
