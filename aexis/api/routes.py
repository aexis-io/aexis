import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional
import logging
import asyncio

from aexis.core import load_network_data

from ..core.system import AexisSystem
from ..core.errors import handle_exception


logger = logging.getLogger(__name__)


class SystemAPI:
    """API layer that proxies requests to core system"""
    
    def __init__(self, system: AexisSystem):
        self.system = system
        self.app = FastAPI(
            title="AEXIS System API",
            description="Core system API for AEXIS transportation network",
            version="1.0.0"
        )
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self.app.get("/api/system/status")
        async def get_system_status():
            """Get overall system status"""
            try:
                return self.system.get_system_state()
            except Exception as e:
                error_details = handle_exception(e, "SystemAPI")
                raise HTTPException(status_code=500, detail=error_details.message)
        
        @self.app.get("/api/system/metrics")
        async def get_system_metrics():
            """Get system metrics"""
            try:
                return self.system.metrics
            except Exception as e:
                error_details = handle_exception(e, "SystemAPI")
                raise HTTPException(status_code=500, detail=error_details.message)
        
        @self.app.get("/api/pods")
        async def get_all_pods():
            """Get all pod states"""
            try:
                return {
                    pod_id: pod.get_state() 
                    for pod_id, pod in self.system.pods.items()
                }
            except Exception as e:
                error_details = handle_exception(e, "SystemAPI")
                raise HTTPException(status_code=500, detail=error_details.message)
        
        @self.app.get("/api/pods/{pod_id}")
        async def get_pod(pod_id: str):
            """Get specific pod state"""
            try:
                pod_state = self.system.get_pod_state(pod_id)
                if not pod_state:
                    raise HTTPException(status_code=404, detail="Pod not found")
                return pod_state
            except HTTPException:
                raise
            except Exception as e:
                error_details = handle_exception(e, "SystemAPI")
                raise HTTPException(status_code=500, detail=error_details.message)
        
        @self.app.get("/api/stations")
        async def get_all_stations():
            """Get all station states"""
            try:
                return {
                    station_id: station.get_state() 
                    for station_id, station in self.system.stations.items()
                }
            except Exception as e:
                error_details = handle_exception(e, "SystemAPI")
                raise HTTPException(status_code=500, detail=error_details.message)
        
        @self.app.get("/api/stations/{station_id}")
        async def get_station(station_id: str):
            """Get specific station state"""
            try:
                station_state = self.system.get_station_state(station_id)
                if not station_state:
                    raise HTTPException(status_code=404, detail="Station not found")
                return station_state
            except HTTPException:
                raise
            except Exception as e:
                error_details = handle_exception(e, "SystemAPI")
                raise HTTPException(status_code=500, detail=error_details.message)

        @self.app.post("/api/manual/passenger")
        async def inject_passenger(request: Dict):
            try:
                origin = request.get('origin')
                dest = request.get('destination')
                count = request.get('count', 1)
                # Validation
                if not origin or not dest:
                    raise HTTPException(status_code=400, detail="Missing origin or destination")
                
                await self.system.inject_passenger_request(origin, dest, count)
                return {"status": "success", "message": f"Injected {count} passengers"}
            except Exception as e:
                error_details = handle_exception(e, "SystemAPI")
                raise HTTPException(status_code=500, detail=error_details.message)

        @self.app.post("/api/manual/cargo")
        async def inject_cargo(request: Dict):
            logger.info('Injecting cargo payload => {request}')
            try:
                origin = request.get('origin')
                dest = request.get('destination')
                weight = request.get('weight', 100.0)
                if not origin or not dest:
                    raise HTTPException(status_code=400, detail="Missing origin or destination")
                
                await self.system.inject_cargo_request(origin, dest, weight)
                return {"status": "success", "message": "Injected cargo request"}
            except Exception as e:
                error_details = handle_exception(e, "SystemAPI")
                raise HTTPException(status_code=500, detail=error_details.message)

        @self.app.get("/api/network")
        async def get_network():
            """Get network topology data"""
            try:
                data = self.get_network_data()
                if data is None:
                    raise HTTPException(status_code=404, detail="Network data not found")
                return data
            except HTTPException:
                raise
            except Exception as e:
                error_details = handle_exception(e, "SystemAPI")
                raise HTTPException(status_code=500, detail=error_details.message)
    
    def get_network_data(self) -> Dict | None:
        path = os.getenv('AEXIS_NETWORK_DATA', 'aexis/network.json')
        return load_network_data(path)


    def get_app(self) -> FastAPI:
        """Get FastAPI application instance"""
        return self.app
