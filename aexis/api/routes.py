from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional
import logging
import asyncio

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
    
    def get_app(self) -> FastAPI:
        """Get FastAPI application instance"""
        return self.app
