import asyncio
import os
import logging
from typing import Dict, List, Optional
from datetime import datetime

import random
from .model import SystemSnapshot
from .message_bus import MessageBus
from .pod import Pod
from .station import Station, PassengerGenerator, CargoGenerator
from .ai_provider import AIProviderFactory
from .errors import handle_exception
from . import load_network_data


logger = logging.getLogger(__name__)


class AexisSystem:
    """Main system coordinator for AEXIS transportation network"""
    
    def __init__(self):
        self.message_bus = MessageBus(
            redis_url=os.getenv('REDIS_URL', 'redis://localhost:6379'),
            password=os.getenv('REDIS_PASSWORD')
        )
        self.ai_provider = None
        self.pods = {}
        self.stations = {}
        self.passenger_generator = None
        self.cargo_generator = None
        self.running = False
        self.start_time = None
        
        # System metrics
        self.metrics = {
            'total_pods': 0,
            'active_pods': 0,
            'total_stations': 0,
            'operational_stations': 0,
            'pending_passengers': 0,
            'pending_cargo': 0,
            'average_wait_time': 0.0,
            'system_efficiency': 0.0,
            'throughput_per_hour': 0,
            'fallback_usage_rate': 0.0
        }
        
        # Configuration
        self.pod_count = int(os.getenv('POD_COUNT', '25'))
        self.station_count = int(os.getenv('STATION_COUNT', '8'))
        self.snapshot_interval = int(os.getenv('SNAPSHOT_INTERVAL', '300'))  # 5 minutes
        
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
            
            logger.info(f"AEXIS system initialized with {len(self.stations)} stations and {len(self.pods)} pods")
            return True
            
        except Exception as e:
            error_details = handle_exception(e, "AexisSystem")
            logger.error(f"System initialization failed: {error_details.message}")
            return False
    
    async def _initialize_ai_provider(self):
        """Initialize AI provider based on configuration"""
        try:
            ai_type = os.getenv('AI_PROVIDER', 'mock').lower()
            
            if ai_type == 'gemini':
                api_key = os.getenv('GEMINI_API_KEY')
                if not api_key:
                    logger.warning("Gemini API key not provided, using mock provider")
                    ai_type = 'mock'
                else:
                    from google import genai
                    client = genai.Client(api_key=api_key)
                    self.ai_provider = AIProviderFactory.create_provider('gemini', client=client)
                    logger.info("Gemini AI provider initialized")
                    return
            
            # Default to mock provider
            self.ai_provider = AIProviderFactory.create_provider(ai_type)
            logger.info(f"{ai_type.title()} AI provider initialized")
            
        except Exception as e:
            logger.debug(f"AI provider initialization failed: {e}", exc_info=True)
            # Fallback to mock provider
            self.ai_provider = AIProviderFactory.create_provider('mock')
            logger.info("Fallback to mock AI provider")
    
    async def start(self):
        """Start the system"""
        if not await self.initialize():
            return False
        
        self.running = True
        
        # Start message bus listening
        message_bus_task = asyncio.create_task(self.message_bus.start_listening())
        
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
            generator_tasks.append(asyncio.create_task(self.passenger_generator.start()))
        if self.cargo_generator:
            generator_tasks.append(asyncio.create_task(self.cargo_generator.start()))
        
        # Start system monitoring
        monitor_task = asyncio.create_task(self._system_monitor())
        
        # Start periodic decision making
        decision_task = asyncio.create_task(self._periodic_decision_making())
        
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
                return_exceptions=True
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
        """Create station instances from network.json nodes"""
        network_path = os.getenv('AEXIS_NETWORK_DATA', 'aexis/network.json')
        network_data = load_network_data(network_path)
        
        if not network_data or 'nodes' not in network_data:
            logger.warning("No network data found, falling back to generated stations")
            # Fallback to old behavior
            station_ids = [f"station_{i:03d}" for i in range(1, self.station_count + 1)]
            for station_id in station_ids:
                station = Station(self.message_bus, station_id)
                station.connected_stations = self._get_connected_stations(station_id, station_ids)
                self.stations[station_id] = station
            return
        
        # Build stations from network nodes
        nodes = network_data['nodes']
        
        # First pass: create all stations
        for node in nodes:
            station_id = f"station_{node['id']}"
            station = Station(self.message_bus, station_id)
            print('Loaded station: ' + station_id)
            
            # Store coordinate for potential future use
            station.coordinate = node.get('coordinate', {'x': 0, 'y': 0})
            
            self.stations[station_id] = station
        
        # Second pass: set connected stations from adjacency
        for node in nodes:
            station_id = f"station_{node['id']}"
            station = self.stations.get(station_id)
            if station:
                connected = []
                for adj in node.get('adj', []):
                    connected_station_id = f"station_{adj['node_id']}"
                    if connected_station_id in self.stations:
                        connected.append(connected_station_id)
                station.connected_stations = connected
                logger.info(f"Created station: {station_id} connected to {connected}")
        
        # Update station_count to reflect actual count
        self.station_count = len(self.stations)
    
    async def _create_pods(self):
        """Create pod instances"""
        for i in range(1, self.pod_count + 1):
            pod_id = f"pod_{i:03d}"
            
            # Create pod with AI provider
            pod = Pod(self.message_bus, pod_id, self.ai_provider)
            
            # Assign initial station (distribute pods across stations)
            station_index = (i - 1) % len(self.stations)
            station_ids = list(self.stations.keys())
            pod.location = station_ids[station_index]
            
            self.pods[pod_id] = pod
            logger.info(f"Created pod: {pod_id} at {pod.location}")
    
    async def _setup_generators(self):
        """Setup passenger and cargo generators"""
        station_ids = list(self.stations.keys())
        
        self.passenger_generator = PassengerGenerator(self.message_bus, station_ids)
        self.cargo_generator = CargoGenerator(self.message_bus, station_ids)
        
        logger.info("Setup passenger and cargo generators")
    
    def _get_connected_stations(self, station_id: str, all_stations: List[str]) -> List[str]:
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
            if all_stations[nearest_hub_idx] not in connected and nearest_hub_idx != station_index:
                connected.append(all_stations[nearest_hub_idx])

        # 3. Random 'Shortcut' (deterministic based on ID to remain consistent)
        import hashlib
        hash_val = int(hashlib.md5(f"{station_id}_salt".encode()).hexdigest(), 16)
        random_offset = (hash_val % (total_stations - 3)) + 2 # Avoid self, prev, next
        random_idx = (station_index + random_offset) % total_stations
        target = all_stations[random_idx]
        if target not in connected and target != station_id:
            connected.append(target)
            
        return list(set(connected)) # Deduplicate
    
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
                    if pod.status.value == 'idle':
                        await pod.make_decision()
                
                # Wait before next round
                await asyncio.sleep(30)  # Every 30 seconds
                
            except Exception as e:
                logger.debug(f"Periodic decision making error: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    async def _update_metrics(self):
        """Update system metrics"""
        # Count active pods
        active_pods = sum(1 for pod in self.pods.values() if pod.status.value != 'maintenance')
        
        # Count operational stations
        operational_stations = sum(1 for station in self.stations.values() if station.status.value == 'operational')
        
        # Count pending requests
        pending_passengers = sum(len(station.passenger_queue) for station in self.stations.values())
        pending_cargo = sum(len(station.cargo_queue) for station in self.stations.values())
        
        # Calculate average wait time
        wait_times = [station.average_wait_time for station in self.stations.values() if station.average_wait_time > 0]
        avg_wait_time = sum(wait_times) / len(wait_times) if wait_times else 0.0
        
        # Calculate system efficiency (simplified)
        total_processed = sum(station.total_passengers_processed + station.total_cargo_processed for station in self.stations.values())
        total_requests = total_processed + pending_passengers + pending_cargo
        system_efficiency = total_processed / total_requests if total_requests > 0 else 0.0
        
        # Calculate throughput per hour
        if self.start_time:
            hours_running = (datetime.now() - self.start_time).total_seconds() / 3600
            throughput_per_hour = total_processed / hours_running if hours_running > 0 else 0
        else:
            throughput_per_hour = 0
        
        # Calculate fallback rate
        total_decisions = sum(len(pod.decision_engine.decision_history) for pod in self.pods.values())
        fallback_usage_rate = 0.0
        if total_decisions > 0:
            fallback_decisions = sum(
                sum(1 for d in pod.decision_engine.decision_history if d.fallback_used)
                for pod in self.pods.values()
            )
            fallback_usage_rate = fallback_decisions / total_decisions
        
        # Update metrics
        self.metrics.update({
            'total_pods': len(self.pods),
            'active_pods': active_pods,
            'total_stations': len(self.stations),
            'operational_stations': operational_stations,
            'pending_passengers': pending_passengers,
            'pending_cargo': pending_cargo,
            'average_wait_time': avg_wait_time,
            'system_efficiency': system_efficiency,
            'throughput_per_hour': throughput_per_hour,
            'fallback_usage_rate': fallback_usage_rate
        })
    
    async def _publish_snapshot(self):
        """Publish system snapshot"""
        snapshot = SystemSnapshot(
            system_state=self.metrics.copy()
        )
        
        await self.message_bus.publish_event(
            MessageBus.get_event_channel(snapshot.event_type),
            snapshot
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
    
    def get_system_state(self) -> Dict:
        """Get complete system state"""
        return {
            'system_id': 'aexis_main',
            'timestamp': datetime.now().isoformat(),
            'running': self.running,
            'uptime_seconds': (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
            'metrics': self.metrics,
            'stations': {sid: station.get_state() for sid, station in self.stations.items()},
            'pods': {pid: pod.get_state() for pid, pod in self.pods.items()}
        }
    
    def get_pod_state(self, pod_id: str) -> Optional[Dict]:
        """Get specific pod state"""
        pod = self.pods.get(pod_id)
        return pod.get_state() if pod else None
    
    async def inject_passenger_request(self, origin_id: str, dest_id: str, count: int = 1):
        """Manually inject passenger request"""
        if self.passenger_generator:
            for _ in range(count):
                # Manually create request via generator logic or directly to event bus
                # Direct event bus is cleaner
                passenger_id = f"manual_p_{datetime.now().strftime('%H%M%S')}_{random.randint(100,999)}"
                event = self.passenger_generator._create_manual_event(passenger_id, origin_id, dest_id)
                await self.message_bus.publish_event(
                    MessageBus.get_event_channel(event.event_type),
                    event
                )
                logger.info(f"Manually injected passenger {passenger_id} at {origin_id} -> {dest_id}")

    async def inject_cargo_request(self, origin_id: str, dest_id: str, weight: float = 100.0):
        """Manually inject cargo request"""
        if self.cargo_generator:
             request_id = f"manual_c_{datetime.now().strftime('%H%M%S')}_{random.randint(100,999)}"
             event = self.cargo_generator._create_manual_event(request_id, origin_id, dest_id, weight)
             await self.message_bus.publish_event(
                MessageBus.get_event_channel(event.event_type),
                event
             )
             print(f"Manually injected cargo {request_id} at {origin_id} -> {dest_id}")
    
    def get_station_state(self, station_id: str) -> Optional[Dict]:
        """Get specific station state"""
        station = self.stations.get(station_id)
        return station.get_state() if station else None
