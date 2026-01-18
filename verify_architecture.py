import asyncio
import httpx
import sys
import time
import signal
import subprocess
import os

async def verify_services():
    print("Verifying AEXIS Architecture Split...")
    
    async with httpx.AsyncClient() as client:
        # 1. Check Core API directly (Port 8001)
        print("\n1. Checking Core API (Direct access)...")
        try:
            resp = await client.get("http://localhost:8001/api/system/status")
            if resp.status_code == 200:
                print("✅ Core API is accessible directly")
                data = resp.json()
                print(f"   System ID: {data.get('system_id')}")
            else:
                print(f"❌ Core API returned {resp.status_code}")
                return False
        except Exception as e:
            print(f"❌ Core API failed: {e}")
            return False

        # 2. Check Dashboard availability (Port 8000)
        print("\n2. Checking Dashboard (UI serving)...")
        try:
            resp = await client.get("http://localhost:8000/")
            if resp.status_code == 200 and "<!DOCTYPE html>" in resp.text:
                print("✅ Dashboard is serving HTML")
            else:
                print(f"❌ Dashboard did not serve HTML correctly (Status: {resp.status_code})")
                return False
        except Exception as e:
            print(f"❌ Dashboard failed: {e}")
            return False

        # 3. Check Proxy Functionality (Dashboard -> API)
        print("\n3. Checking Proxy (Dashboard -> Core API)...")
        try:
            resp = await client.get("http://localhost:8000/api/system/status")
            if resp.status_code == 200:
                data = resp.json()
                if data.get('system_id') == 'aexis_main':
                    print("✅ Proxy is working! Received system state via Dashboard port")
                else:
                    print(f"❌ Proxy returned unexpected data: {data}")
                    return False
            else:
                print(f"❌ Proxy request failed (Status: {resp.status_code})")
                return False
        except Exception as e:
            print(f"❌ Proxy test failed: {e}")
            return False

    print("\n✅ VERIFICATION SUCCESSFUL")
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Run test only
        asyncio.run(verify_services())
    else:
        print("This script is intended to be run while services are running.")
        print("Run './run_services.sh' in one terminal, and 'python3 verify_architecture.py test' in another.")
