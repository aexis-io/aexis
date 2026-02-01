from .network import (
    Network,
    NetworkAdjacency,
    NetworkContext,
    NetworkNode,
    load_network_data,
)
import asyncio
import json
import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from .ai_provider import AIProviderFactory
from .errors import handle_exception
from .message_bus import MessageBus
from .model import SystemSnapshot
from .pod import CargoPod, PassengerPod, Pod
from .routing import RoutingProvider
from .station import CargoGenerator, PassengerGenerator, Station

logger = logging.getLogger(__name__)


class AexisConfig:
    """Configuration for Aexis system"""

    def __init__(
        self, debug: bool = False, network_data_path: str | None = None, **kwargs
    ):
        self.debug = debug
        self.network_data_path = network_data_path
        for key, value in kwargs.items():
            setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key with optional default.
        config.get('stations.count', 10)
        will parse the dict structure to get nested values.
        """
        keys = key.split(".")
        value = self
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                value = getattr(value, k, default)
            if value is default:
                break
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "debug": self.debug,
            "network_data_path": self.network_data_path,
            **{
                k: v
                for k, v in self.__dict__.items()
                if k not in ["debug", "network_data_path"]
            },
        }


class SystemContext:
    """Centralized system context managing configuration and network state"""

    _instance = None
    _initialized = False
    _lock = None

    def __init__(self):
        if not SystemContext._initialized:
            self._config = None
            self._network_context = None
            self._config_path = None
            SystemContext._initialized = True

    @classmethod
    async def initialize(cls, config_path: str = "aexis/aexis.json") -> 'SystemContext':
        """Initialize SystemContext with configuration from aexis.json"""
        if cls._instance is None:
            import threading
            cls._lock = threading.Lock()

            with cls._lock:
                if cls._instance is None:
                    instance = cls()
                    await instance._load_configuration(config_path)
                    cls._instance = instance

        return cls._instance

    @classmethod
    def get_instance(cls) -> 'SystemContext':
        """Get the SystemContext instance (must be initialized first)"""
        if cls._instance is None:
            raise RuntimeError(
                "SystemContext must be initialized before use. Call await SystemContext.initialize() first.")
        return cls._instance

    @classmethod
    def set_instance(cls, instance: 'SystemContext'):
        """Set the SystemContext instance (for testing)"""
        cls._instance = instance
        cls._initialized = True

    async def _load_configuration(self, config_path: str):
        """Load configuration from aexis.json"""
        self._config_path = config_path

        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)

            # Extract configuration section
            config_section = config_data.get('config', {})

            # Initialize AexisConfig with loaded data
            self._config = AexisConfig(
                debug=config_section.get('debug', False),
                network_data_path=config_section.get(
                    'networkDataPath', 'aexis/network.json'),
                **{k: v for k, v in config_section.items() if k not in ['debug', 'networkDataPath']}
            )

            # Load network data and initialize NetworkContext
            network_path = self._config.network_data_path
            network_data = load_network_data(network_path)
            self._network_context = NetworkContext(network_data)

            logger.info(
                f"SystemContext initialized with config: {config_path}")

        except FileNotFoundError:
            logger.warning(
                f"Configuration file not found: {config_path}, using defaults")
            self._config = AexisConfig()
            self._network_context = NetworkContext()
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}, using defaults")
            self._config = AexisConfig()
            self._network_context = NetworkContext()

    def get_config(self) -> AexisConfig:
        """Get system configuration"""
        if self._config is None:
            raise RuntimeError(
                "Configuration not loaded. Call await SystemContext.initialize() first.")
        return self._config

    def get_network_context(self) -> NetworkContext:
        """Get network context"""
        if self._network_context is None:
            raise RuntimeError(
                "Network context not initialized. Call await SystemContext.initialize() first.")
        return self._network_context

    def reload_configuration(self) -> bool:
        """Reload configuration from file (synchronous version for compatibility)"""
        try:
            with open(self._config_path, 'r') as f:
                config_data = json.load(f)

            config_section = config_data.get('config', {})

            # Update existing configuration
            for key, value in config_section.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)

            logger.info("Configuration reloaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            return False


class AexisSystem:
    """Main system coordinator for AEXIS transportation network"""

    def __init__(self, system_context: SystemContext = None):
        # Use provided SystemContext or get the instance
        self.system_context = system_context or SystemContext.get_instance()
        self.config = self.system_context.get_config()
        self.network_context = self.system_context.get_network_context()

        # Initialize message bus with configuration
        self.message_bus = MessageBus(
            redis_url=self.config.get('redis.url', "redis://localhost:6379"),
            password=self.config.get('redis.password'),
        )
        self.ai_provider = None
        self.pods: Mapping[str, Pod] =  {}
        self.stations = {}
        self.passenger_generator = None
        self.cargo_generator = None
        self.running = False
        self.start_time = None

        # System metrics
        self.metrics = {
            "total_pods": 0,
            "active_pods": 0,
            "total_stations": 0,
            "operational_stations": 0,
            "pending_passengers": 0,
            "pending_cargo": 0,
            "average_wait_time": 0.0,
            "system_efficiency": 0.0,
            "throughput_per_hour": 0,
            "fallback_usage_rate": 0.0,
        }

        # Configuration from SystemContext instead of environment variables
        self.pod_count = self.config.get('pods.count', 25)
        self.cargo_percentage = self.config.get(
            'pods.cargoPercentage', 50)  # 0-100
        self.station_count = self.config.get('stations.count', 8)
        self.snapshot_interval = self.config.get(
            'system.snapshotInterval', 300)  # 5 minutes

    async def initialize(self) -> bool:
        """Initialize system"""
        try:
            # Connect to Redis
            if not await self.message_bus.connect():
                logger.error("Failed to connect to Redis message bus")
                return False

            # Initialize AI provider
            await self._initialize_ai_provider()

            # Create stations
            await self._create_stations()

            # Create pods
            await self._create_pods()

            # Setup generators
            await self._setup_generators()

            # Start system monitoring
            self.start_time = datetime.now()

            logger.info(
                f"AEXIS system initialized with {len(self.stations)} stations and {len(self.pods)} pods"
            )
            return True

        except Exception as e:
            error_details = handle_exception(e, "AexisSystem")
            logger.error(
                f"System initialization failed: {error_details.message}")
            return False

    async def _initialize_ai_provider(self):
        """Initialize AI provider based on configuration"""
        try:
            ai_type = self.config.get('ai.provider', 'mock').lower()

            if ai_type == "gemini":
                api_key = self.config.get(
                    'ai.gemini.api_key') or os.getenv("GEMINI_API_KEY")
                if not api_key:
                    logger.warning(
                        "Gemini API key not provided, using mock provider")
                    ai_type = "mock"
                else:
                    from google import genai

                    client = genai.Client(api_key=api_key)
                    self.ai_provider = AIProviderFactory.create_provider(
                        "gemini", client=client
                    )
                    logger.info("Gemini AI provider initialized")
                    return

            # Default to mock provider
            self.ai_provider = AIProviderFactory.create_provider(ai_type)
            logger.info(f"{ai_type.title()} AI provider initialized")

        except Exception as e:
            logger.debug(
                f"AI provider initialization failed: {e}", exc_info=True)
            # Fallback to mock provider
            self.ai_provider = AIProviderFactory.create_provider("mock")
            logger.info("Fallback to mock AI provider")

    async def start(self):
        """Start the system"""
        if not await self.initialize():
            return False

        self.running = True

        # Start message bus listening
        message_bus_task = asyncio.create_task(
            self.message_bus.start_listening())

        # Start all stations
        station_tasks = []
        for station in self.stations.values():
            station_tasks.append(asyncio.create_task(station.start()))

        # Start all pods
        pod_tasks = []
        for pod in self.pods.values():
            pod_tasks.append(asyncio.create_task(pod.start()))

        # Start generators
        generator_tasks = []
        if self.passenger_generator:
            generator_tasks.append(
                asyncio.create_task(self.passenger_generator.start())
            )
        if self.cargo_generator:
            generator_tasks.append(asyncio.create_task(
                self.cargo_generator.start()))

        # Start system monitoring
        monitor_task = asyncio.create_task(self._system_monitor())

        # Start periodic decision making
        decision_task = asyncio.create_task(self._periodic_decision_making())

        # Start pod movement simulation (Phase 1)
        movement_task = asyncio.create_task(self._simulate_pod_movement())

        logger.info("AEXIS system started")

        try:
            # Wait for all tasks
            await asyncio.gather(
                message_bus_task,
                *station_tasks,
                *pod_tasks,
                *generator_tasks,
                monitor_task,
                decision_task,
                movement_task,
                return_exceptions=True,
            )
        except KeyboardInterrupt:
            logger.info("Shutdown signal received")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Shutdown the system"""
        self.running = False

        logger.info("Shutting down AEXIS system...")

        # Stop generators
        if self.passenger_generator:
            await self.passenger_generator.stop()
        if self.cargo_generator:
            await self.cargo_generator.stop()

        # Stop all pods
        for pod in self.pods.values():
            await pod.stop()

        # Stop all stations
        for station in self.stations.values():
            await station.stop()

        # Stop message bus
        await self.message_bus.stop_listening()
        await self.message_bus.disconnect()

        logger.info("AEXIS system shutdown complete")

    async def _create_stations(self):
        """Create station instances from network.json nodes using SystemContext"""
        # NetworkContext is already initialized in SystemContext
        network_data = None

        # Try to get network data from the already initialized NetworkContext
        if hasattr(self.network_context, 'network_graph') and self.network_context.network_graph.nodes():
            # Extract network data from NetworkContext for station creation
            network_data = {"nodes": []}
            for node_id in self.network_context.network_graph.nodes():
                # Extract node ID from station_XXX format
                if node_id.startswith("station_"):
                    station_num = node_id[8:]  # Remove "station_" prefix
                    pos = self.network_context.station_positions.get(
                        node_id, {"x": 0, "y": 0})

                    # Get adjacency information
                    adj = []
                    if self.network_context.network_graph.has_node(node_id):
                        for neighbor in self.network_context.network_graph.neighbors(node_id):
                            if neighbor.startswith("station_"):
                                neighbor_num = neighbor[8:]
                                weight = self.network_context.network_graph[node_id][neighbor].get(
                                    'weight', 1.0)
                                adj.append(
                                    {"node_id": neighbor_num, "weight": weight})

                    network_data["nodes"].append({
                        "id": station_num,
                        "label": station_num,
                        "coordinate": {"x": pos[0], "y": pos[1]},
                        "adj": adj
                    })

        if not network_data or "nodes" not in network_data:
            logger.warning(
                "No network data found in SystemContext, falling back to generated stations")
            # Fallback to old behavior
            station_ids = [f"station_{i:03d}" for i in range(
                1, self.station_count + 1)]
            for station_id in station_ids:
                station = Station(self.message_bus, station_id)
                station.connected_stations = self._get_connected_stations(
                    station_id, station_ids
                )
                self.stations[station_id] = station
            return

        # Build stations from network nodes
        nodes = network_data["nodes"]

        # First pass: create all stations
        for node in nodes:
            station_id = f"station_{node['id']}"
            station = Station(self.message_bus, station_id)
            logger.debug(f"Loaded station: {station_id}")

            # Store coordinate for potential future use
            station.coordinate = node.get("coordinate", {"x": 0, "y": 0})

            self.stations[station_id] = station

        # Second pass: set connected stations from adjacency
        for node in nodes:
            station_id = f"station_{node['id']}"
            station = self.stations.get(station_id)
            if station:
                connected = []
                for adj in node.get("adj", []):
                    connected_station_id = f"station_{adj['node_id']}"
                    if connected_station_id in self.stations:
                        connected.append(connected_station_id)
                station.connected_stations = connected
                logger.info(
                    f"Created station: {station_id} connected to {connected}")

        # Update station_count to reflect actual count
        self.station_count = len(self.stations)

    async def _create_pods(self):
        """Create pod instances with network positioning on edges

        PHASE 1: Pods spawn at random positions on network edges
        Pod types (passenger/cargo) determined by cargoPercentage from config
        """
        for i in range(1, self.pod_count + 1):
            pod_id = f"pod_{i:03d}"

            # Create routing provider for this pod
            # Pod layer is agnostic: it doesn't know if routing uses AI or offline strategies
            # The routing provider transparently handles both
            routing_provider = self._create_routing_provider(pod_id)

            # Determine pod type based on config percentage
            # If cargoPercentage=50, first 50% are cargo, rest are passenger
            pod_index_percentage = ((i - 1) / self.pod_count) * 100
            is_cargo = pod_index_percentage < self.cargo_percentage

            if is_cargo:
                pod = CargoPod(self.message_bus, pod_id, routing_provider)
            else:
                pod = PassengerPod(self.message_bus, pod_id, routing_provider)

            # PHASE 1: Spawn pod at random network edge
            edge_id, coordinate = self.network_context.spawn_pod_at_random_edge()

            # Set initial position
            # Check if we fell back to a station ID
            if edge_id in self.network_context.station_positions:
                # Fallback: spawned at station
                from .model import LocationDescriptor
                pod.location_descriptor = LocationDescriptor(
                    "station", node_id=edge_id, coordinate=coordinate)
            else:
                # Spawned on edge - set up for continuous movement
                from .model import LocationDescriptor, PodStatus

                # Retrieve the actual EdgeSegment object
                edge_segment = self.network_context.edges.get(edge_id)

                if edge_segment:
                    pod.current_segment = edge_segment
                    # Approximate progress based on coordinate distance from start
                    # (Simple linear approximation for initialization)
                    pod.segment_progress = edge_segment.start_coord.distance_to(coordinate)

                    pod.status = PodStatus.EN_ROUTE
                    pod.location_descriptor = LocationDescriptor(
                        "edge",
                        edge_id=edge_id,
                        coordinate=coordinate,
                        distance_on_edge=pod.segment_progress
                    )

                    # Assign a random destination so it keeps moving after this edge
                    # Find a random station that is NOT the start/end of current edge
                    all_stations = list(self.network_context.station_positions.keys())
                    if all_stations:
                        import random
                        dest = random.choice(all_stations)
                        # We can't easily call navigate_to_station because we are mid-edge.
                        # For now, let's just let it finish this edge.
                        # Logic in 'update' handles route completion.
                else:
                     logger.warning(f"Spawned on unknown edge {edge_id}")


            self.pods[pod_id] = pod
            pod_type = "Cargo" if is_cargo else "Passenger"
            logger.info(
                f"Created {pod_type}Pod: {pod_id} at edge {edge_id} @ position ({coordinate.x}, {coordinate.y})"
            )

            # Publish initial position update for UI rendering
            # Use asyncio.create_task to fire-and-forget without blocking pod creation
            asyncio.create_task(pod._publish_position_update())

    def _create_routing_provider(self, pod_id: str) -> RoutingProvider:
        """Create a configured routing provider for a pod using SystemContext

        Returns a RoutingProvider with:
        - Offline routing as primary strategy
        - AI routing as fallback (if AI provider available)

        This encapsulates the routing strategy configuration so pods don't need to know about it.
        """
        routing_provider = RoutingProvider()

        # Always add offline router as primary
        # Pass the NetworkContext from SystemContext to avoid singleton access
        from .routing import OfflineRouter
        offline_router = OfflineRouter(self.network_context)
        routing_provider.add_router(offline_router)

        # Add AI router as fallback if AI provider is available
        if self.ai_provider:
            from .routing import AIRouter, OfflineRoutingStrategy
            ai_router = AIRouter(pod_id, self.ai_provider,
                                 OfflineRoutingStrategy(self.network_context))
            routing_provider.add_router(ai_router)

        return routing_provider

    async def _setup_generators(self):
        """Setup passenger and cargo generators"""
        station_ids = list(self.stations.keys())

        self.passenger_generator = PassengerGenerator(
            self.message_bus, station_ids)
        self.cargo_generator = CargoGenerator(self.message_bus, station_ids)

        logger.info("Setup passenger and cargo generators")

    def _get_connected_stations(
        self, station_id: str, all_stations: list[str]
    ) -> list[str]:
        """Get connected stations creating a complex mesh topology"""
        station_index = all_stations.index(station_id)
        total_stations = len(all_stations)
        connected = []

        # 1. Ring connections (Next and Prev)
        next_index = (station_index + 1) % total_stations
        prev_index = (station_index - 1) % total_stations
        connected.append(all_stations[next_index])
        connected.append(all_stations[prev_index])

        # 2. 'Hub' connections (Every 4th station is a hub connected to many)
        if station_index % 4 == 0:
            # Connect to other hubs
            for i in range(0, total_stations, 4):
                if i != station_index:
                    connected.append(all_stations[i])
        else:
            # Connect to nearest hub
            nearest_hub_idx = (station_index // 4) * 4
            if (
                all_stations[nearest_hub_idx] not in connected
                and nearest_hub_idx != station_index
            ):
                connected.append(all_stations[nearest_hub_idx])

        # 3. Random 'Shortcut' (deterministic based on ID to remain consistent)
        import hashlib

        hash_val = int(hashlib.md5(
            f"{station_id}_salt".encode()).hexdigest(), 16)
        random_offset = (hash_val % (total_stations - 3)) + \
            2  # Avoid self, prev, next
        random_idx = (station_index + random_offset) % total_stations
        target = all_stations[random_idx]
        if target not in connected and target != station_id:
            connected.append(target)

        return list(set(connected))  # Deduplicate

    async def _system_monitor(self):
        """Monitor system metrics and publish snapshots"""
        while self.running:
            try:
                # Update metrics
                await self._update_metrics()

                # Publish periodic snapshot
                await self._publish_snapshot()

                # Log system status
                await self._log_system_status()

                await asyncio.sleep(self.snapshot_interval)

            except Exception as e:
                logger.debug(f"System monitor error: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait before retrying

    async def _periodic_decision_making(self):
        """Trigger periodic decision making for pods"""
        while self.running:
            try:
                # Trigger decision making for idle pods
                for pod in self.pods.values():
                    if pod.status.value == "idle":
                        await pod.make_decision()

                # Wait before next round
                await asyncio.sleep(30)  # Every 30 seconds

            except Exception as e:
                logger.debug(
                    f"Periodic decision making error: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _simulate_pod_movement(self):
        """Simulate pod movement with continuous path integration
        
        Uses precise delta-time calculation to ensure smooth, speed-consistent movement
        regardless of the actual update frequency (server lag resilience).
        """
        target_interval = 5.0  # Target 10 Hz . 500ms
        loop = asyncio.get_running_loop()
        last_time = loop.time()

        while self.running:
            try:
                now = loop.time()
                dt = now - last_time
                last_time = now
                
                # Cap dt to avoid massive jumps if thread hangs (e.g. max 1.0s)
                dt = min(dt, 1.0)
                print(f"Updating pods position")
                # Update all pods
                # In Phase 2, this could be parallelized if pod count > 1000
                for pod in self.pods.values():
                    await pod.update(dt)

                # Sleep strict remainder to maintain roughly target rate
                # processing_time = loop.time() - now
                # sleep_time = max(0.01, target_interval - processing_time)
                
                # Simple sleep is fine for now, dt handles the physics correctness
                await asyncio.sleep(target_interval)

            except Exception as e:
                logger.debug(
                    f"Pod movement simulation error: {e}", exc_info=True)
                await asyncio.sleep(target_interval)

    async def _update_metrics(self):
        """Update system metrics"""
        # Count active pods
        active_pods = sum(
            1 for pod in self.pods.values() if pod.status.value != "maintenance"
        )

        # Count operational stations
        operational_stations = sum(
            1
            for station in self.stations.values()
            if station.status.value == "operational"
        )

        # Count pending requests
        pending_passengers = sum(
            len(station.passenger_queue) for station in self.stations.values()
        )
        pending_cargo = sum(
            len(station.cargo_queue) for station in self.stations.values()
        )

        # Calculate average wait time
        wait_times = [
            station.average_wait_time
            for station in self.stations.values()
            if station.average_wait_time > 0
        ]
        avg_wait_time = sum(wait_times) / \
            len(wait_times) if wait_times else 0.0

        # Calculate system efficiency (simplified)
        total_processed = sum(
            station.total_passengers_processed + station.total_cargo_processed
            for station in self.stations.values()
        )
        total_requests = total_processed + pending_passengers + pending_cargo
        system_efficiency = (
            total_processed / total_requests if total_requests > 0 else 0.0
        )

        # Calculate throughput per hour
        if self.start_time:
            hours_running = (datetime.now() -
                             self.start_time).total_seconds() / 3600
            throughput_per_hour = (
                total_processed / hours_running if hours_running > 0 else 0
            )
        else:
            throughput_per_hour = 0

        # Calculate fallback rate
        total_decisions = sum(
            len(pod.decision_engine.decision_history) for pod in self.pods.values()
        )
        fallback_usage_rate = 0.0
        if total_decisions > 0:
            fallback_decisions = sum(
                sum(1 for d in pod.decision_engine.decision_history if d.fallback_used)
                for pod in self.pods.values()
            )
            fallback_usage_rate = fallback_decisions / total_decisions

        # Update metrics
        self.metrics.update(
            {
                "total_pods": len(self.pods),
                "active_pods": active_pods,
                "total_stations": len(self.stations),
                "operational_stations": operational_stations,
                "pending_passengers": pending_passengers,
                "pending_cargo": pending_cargo,
                "average_wait_time": avg_wait_time,
                "system_efficiency": system_efficiency,
                "throughput_per_hour": throughput_per_hour,
                "fallback_usage_rate": fallback_usage_rate,
            }
        )

    async def _publish_snapshot(self):
        """Publish system snapshot"""
        snapshot = SystemSnapshot(system_state=self.metrics.copy())

        await self.message_bus.publish_event(
            MessageBus.get_event_channel(snapshot.event_type), snapshot
        )

    async def _log_system_status(self):
        """Log system status"""
        logger.info(
            f"System Status - Pods: {self.metrics['active_pods']}/{self.metrics['total_pods']}, "
            f"Stations: {self.metrics['operational_stations']}/{self.metrics['total_stations']}, "
            f"Queue: {self.metrics['pending_passengers']}P/{self.metrics['pending_cargo']}C, "
            f"Efficiency: {self.metrics['system_efficiency']:.1%}, "
            f"Fallback Rate: {self.metrics['fallback_usage_rate']:.1%}"
        )

    def get_system_state(self) -> dict:
        """Get complete system state"""
        return {
            "system_id": "aexis_main",
            "timestamp": datetime.now().isoformat(),
            "running": self.running,
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds()
            if self.start_time
            else 0,
            "metrics": self.metrics,
            "stations": {
                sid: station.get_state() for sid, station in self.stations.items()
            },
            "pods": {pid: pod.get_state() for pid, pod in self.pods.items()},
        }

    def get_pod_state(self, pod_id: str) -> dict | None:
        """Get specific pod state"""
        pod = self.pods.get(pod_id)
        return pod.get_state() if pod else None

    async def inject_passenger_request(
        self, origin_id: str, dest_id: str, count: int = 1
    ):
        """Manually inject passenger request"""
        if self.passenger_generator:
            for _ in range(count):
                # Manually create request via generator logic or directly to event bus
                # Direct event bus is cleaner
                passenger_id = f"manual_p_{datetime.now().strftime('%H%M%S')}_{random.randint(100, 999)}"
                event = self.passenger_generator._create_manual_event(
                    passenger_id, origin_id, dest_id
                )
                await self.message_bus.publish_event(
                    MessageBus.get_event_channel(event.event_type), event
                )
                logger.info(
                    f"Manually injected passenger {passenger_id} at {origin_id} -> {dest_id}"
                )

    async def inject_cargo_request(
        self, origin_id: str, dest_id: str, weight: float = 100.0
    ):
        """Manually inject cargo request"""
        if self.cargo_generator:
            request_id = f"manual_c_{datetime.now().strftime('%H%M%S')}_{random.randint(100, 999)}"
            event = self.cargo_generator._create_manual_event(
                request_id, origin_id, dest_id, weight
            )
            await self.message_bus.publish_event(
                MessageBus.get_event_channel(event.event_type), event
            )
            print(
                f"Manually injected cargo {request_id} at {origin_id} -> {dest_id}")

    def get_station_state(self, station_id: str) -> dict | None:
        """Get specific station state"""
        station = self.stations.get(station_id)
        return station.get_state() if station else None
