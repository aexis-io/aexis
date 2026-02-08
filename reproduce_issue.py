import asyncio
import logging
import sys
from datetime import datetime

# Setup paths
sys.path.append("/home/godelhaze/dev/megalith/aexis")

from aexis.core.system import AexisSystem, SystemContext
from aexis.core.model import PodStatus

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReproduceDispatch")

async def run_reproduction():
    print("Initializing System...")
    sys_ctx = await SystemContext.initialize()
    system = AexisSystem(sys_ctx)
    
    # Configure for reproduction
    system.pod_count = 1
    system.station_count = 2
    
    await system.initialize()
    
    pod = list(system.pods.values())[0]
    station_ids = list(system.stations.keys())
    origin = station_ids[0]
    dest = station_ids[1]
    
    print(f"Pod {pod.pod_id} initialized at {pod.location}")
    print(f"Stations: {station_ids}")
    
    # 1. Busy the pod manually to simulate being en-route
    print(f"Setting Pod {pod.pod_id} to BUSY state...")
    pod.status = PodStatus.EN_ROUTE
    # We won't start the main simulation loop, so it won't auto-update status
    
    # 2. Inject a request
    print(f"Injecting passenger request at {origin}...")
    await system.inject_passenger_request(origin, dest)
    
    # Allow async events to process
    await asyncio.sleep(1)
    
    # Check if pod has requests (should be None/empty since System ignores busy pods)
    print(f"Pod requests before becoming IDLE: {len(pod._available_requests)}")
    assert len(pod._available_requests) == 0, "System should not assign requests to busy pod"
    
    # 3. "Finish" route and become IDLE
    print(f"Pod {pod.pod_id} becoming IDLE...")
    pod.status = PodStatus.IDLE
    
    # 4. Trigger decision logic (which happens after station arrival usually)
    # In the bug scenario, make_decision is called but _available_requests is empty
    # because it wasn't refreshed.
    print("Pod calling make_decision()...")
    await pod.make_decision()
    
    # 5. Check result
    print(f"Pod decision: {pod.decision}")
    print(f"Pod status: {pod.status}")
    
    if pod.status == PodStatus.IDLE:
        print("\nFAILURE REPRODUCED: Pod remained IDLE despite pending request.")
    else:
        print("\nSUCCESS: Pod picked up request.")

    await system.shutdown()

if __name__ == "__main__":
    asyncio.run(run_reproduction())
