import networkx as nx
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import math

from .model import DecisionContext, Route, Priority


class OfflineRouter:
    """Offline routing algorithm for fallback decision making"""
    
    def __init__(self):
        self.network_graph = None
        self.station_positions = {}
        self._initialize_network()
    
    def _initialize_network(self):
        """Initialize the transportation network graph"""
        # Create a simple network topology
        self.network_graph = nx.Graph()
        
        # Add stations (8 stations in a ring with some cross connections)
        stations = [f"station_{i:03d}" for i in range(1, 9)]
        
        # Station positions for distance calculations
        angle_step = 2 * math.pi / len(stations)
        for i, station in enumerate(stations):
            angle = i * angle_step
            x = 100 * math.cos(angle)
            y = 100 * math.sin(angle)
            self.station_positions[station] = (x, y)
            self.network_graph.add_node(station, pos=(x, y))
        
        # Add edges (ring connections)
        for i in range(len(stations)):
            current = stations[i]
            next_station = stations[(i + 1) % len(stations)]
            distance = self._calculate_distance(current, next_station)
            self.network_graph.add_edge(current, next_station, weight=distance)
        
        # Add some cross connections for efficiency
        cross_connections = [
            ("station_001", "station_004"),
            ("station_002", "station_006"),
            ("station_003", "station_007"),
            ("station_005", "station_008")
        ]
        
        for station1, station2 in cross_connections:
            distance = self._calculate_distance(station1, station2)
            self.network_graph.add_edge(station1, station2, weight=distance)
    
    def _calculate_distance(self, station1: str, station2: str) -> float:
        """Calculate Euclidean distance between stations"""
        pos1 = self.station_positions.get(station1, (0, 0))
        pos2 = self.station_positions.get(station2, (0, 0))
        return math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)
    
    def calculate_optimal_route(self, context: DecisionContext) -> Dict:
        """Calculate optimal route using multi-criteria optimization"""
        
        if not context.available_requests:
            return {
                'route': [context.current_location],
                'duration': 0,
                'distance': 0,
                'confidence': 0.8
            }
        
        # Analyze available requests to determine destinations
        destinations = set()
        for req in context.available_requests:
            destination = req.get('destination')
            if destination and destination != context.current_location:
                destinations.add(destination)
        
        if not destinations:
            return {
                'route': [context.current_location],
                'duration': 0,
                'distance': 0,
                'confidence': 0.8
            }
        
        # Find optimal route visiting all destinations
        optimal_route = self._solve_traveling_salesman(context.current_location, list(destinations))
        
        # Calculate route metrics
        total_distance = self._calculate_route_distance(optimal_route)
        estimated_duration = self._estimate_travel_time(total_distance, context.network_state)
        
        return {
            'route': optimal_route,
            'duration': estimated_duration,
            'distance': total_distance,
            'confidence': 0.75  # Fixed confidence for offline routing
        }
    
    def _solve_traveling_salesman(self, start: str, destinations: List[str]) -> List[str]:
        """Simple TSP solver using nearest neighbor heuristic"""
        if not destinations:
            return [start]
        
        route = [start]
        unvisited = destinations.copy()
        current = start
        
        while unvisited:
            nearest = self._find_nearest_station(current, unvisited)
            route.append(nearest)
            unvisited.remove(nearest)
            current = nearest
        
        return route
    
    def _find_nearest_station(self, current: str, candidates: List[str]) -> str:
        """Find the nearest station from candidates"""
        nearest = candidates[0]
        min_distance = self._calculate_distance(current, nearest)
        
        for station in candidates[1:]:
            distance = self._calculate_distance(current, station)
            if distance < min_distance:
                min_distance = distance
                nearest = station
        
        return nearest
    
    def _calculate_route_distance(self, route: List[str]) -> float:
        """Calculate total distance for a route"""
        total_distance = 0.0
        
        for i in range(len(route) - 1):
            try:
                # Use NetworkX shortest path for accurate distances
                path_length = nx.shortest_path_length(
                    self.network_graph, 
                    route[i], 
                    route[i + 1], 
                    weight='weight'
                )
                total_distance += path_length
            except nx.NetworkXNoPath:
                # Fallback to direct distance
                total_distance += self._calculate_distance(route[i], route[i + 1])
        
        return total_distance
    
    def _estimate_travel_time(self, distance: float, network_state: Dict) -> int:
        """Estimate travel time based on distance and network conditions"""
        # Base speed: 50 units per minute
        base_speed = 50.0
        
        # Adjust for network congestion
        congestion_factor = network_state.get('avg_congestion', 0.0)
        adjusted_speed = base_speed * (1.0 - congestion_factor * 0.5)  # Reduce speed by up to 50%
        
        # Calculate travel time in minutes
        travel_time = distance / adjusted_speed
        
        # Add loading/unloading time (2 minutes per stop)
        stops_time = max(0, len([s for s in network_state.get('route', []) if s != 'start']) - 1) * 2
        
        total_time = travel_time + stops_time
        
        return int(round(total_time))
    
    def select_requests(self, context: DecisionContext) -> Tuple[List[str], List[str]]:
        """Select requests based on capacity and priority"""
        accepted = []
        rejected = []
        
        capacity_used = 0
        weight_used = 0
        
        # Sort requests by priority (descending) then by weight/size (ascending)
        sorted_requests = sorted(
            context.available_requests,
            key=lambda req: (
                -req.get('priority', Priority.NORMAL.value),
                req.get('weight', 0) if req.get('type') == 'cargo' else req.get('group_size', 1)
            )
        )
        
        for req in sorted_requests:
            req_id = req.get('id')
            req_type = req.get('type')
            
            if req_type == 'passenger':
                group_size = req.get('group_size', 1)
                if capacity_used + group_size <= context.capacity_available:
                    accepted.append(req_id)
                    capacity_used += group_size
                else:
                    rejected.append(req_id)
            
            elif req_type == 'cargo':
                weight = req.get('weight', 0)
                if weight_used + weight <= context.weight_available:
                    accepted.append(req_id)
                    weight_used += weight
                else:
                    rejected.append(req_id)
        
        return accepted, rejected
    
    def calculate_route_efficiency(self, route: List[str], requests: List[Dict]) -> float:
        """Calculate efficiency score for a route (0.0-1.0)"""
        if not route or len(route) < 2:
            return 1.0
        
        # Factors for efficiency:
        # 1. Route distance (shorter is better)
        # 2. Request priority fulfillment
        # 3. Capacity utilization
        
        total_distance = self._calculate_route_distance(route)
        
        # Normalize distance (assuming max reasonable distance is 500 units)
        distance_score = max(0, 1.0 - total_distance / 500.0)
        
        # Priority fulfillment score
        priority_score = 0.0
        if requests:
            total_priority = sum(req.get('priority', Priority.NORMAL.value) for req in requests)
            max_possible_priority = len(requests) * Priority.CRITICAL.value
            priority_score = total_priority / max_possible_priority
        
        # Capacity utilization (assuming optimal is 80% utilization)
        # This would need actual capacity data in real implementation
        utilization_score = 0.8  # Placeholder
        
        # Weighted combination
        efficiency = (distance_score * 0.4 + priority_score * 0.4 + utilization_score * 0.2)
        
        return min(1.0, efficiency)
    
    def get_network_state(self) -> Dict:
        """Get current network state for routing decisions"""
        # In real implementation, this would gather real-time data
        return {
            'avg_congestion': 0.2,  # 20% average congestion
            'traffic_levels': {
                'station_001': 0.3,
                'station_002': 0.1,
                'station_003': 0.4,
                'station_004': 0.2,
                'station_005': 0.3,
                'station_006': 0.1,
                'station_007': 0.2,
                'station_008': 0.3
            },
            'blocked_edges': [],  # No blocked edges currently
            'processing_rates': {
                'station_001': 2.5,
                'station_002': 3.0,
                'station_003': 2.0,
                'station_004': 2.8,
                'station_005': 2.2,
                'station_006': 3.1,
                'station_007': 2.6,
                'station_008': 2.9
            }
        }
    
    def validate_route(self, route: List[str]) -> bool:
        """Validate that a route is feasible"""
        if len(route) < 2:
            return True  # Single station is valid
        
        for i in range(len(route) - 1):
            try:
                nx.shortest_path(self.network_graph, route[i], route[i + 1])
            except nx.NetworkXNoPath:
                return False
        
        return True
    
    def get_alternative_routes(self, start: str, end: str, max_alternatives: int = 3) -> List[List[str]]:
        """Get alternative routes between two stations"""
        try:
            # Get all simple paths up to a reasonable length
            all_paths = list(nx.all_simple_paths(
                self.network_graph, 
                start, 
                end, 
                cutoff=6  # Max 6 hops
            ))
            
            # Sort by distance and return top alternatives
            scored_paths = []
            for path in all_paths:
                distance = self._calculate_route_distance(path)
                scored_paths.append((distance, path))
            
            scored_paths.sort(key=lambda x: x[0])
            
            return [path for _, path in scored_paths[:max_alternatives]]
        
        except nx.NetworkXNoPath:
            return []
