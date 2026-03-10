import httpx
import asyncio
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1"

async def test_poc_workflow():
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"--- 🛡️  OpenGuardian PoC Test Workflow [{datetime.now().isoformat()}] ---")

        # 1. Health Check
        print("\n[1/6] Testing System Health...")
        try:
            resp = await client.get(f"{BASE_URL}/health")
            print(f"Status: {resp.status_code}")
            print(json.dumps(resp.json(), indent=2))
        except Exception as e:
            print(f"❌ Health check failed: {e}")

        # 2. Registries & Connectors
        print("\n[2/6] Listing Active Connectors...")
        resp = await client.get(f"{BASE_URL}/connectors")
        print(json.dumps(resp.json(), indent=2))

        # 3. Behavior Summary (The "Story")
        print("\n[3/6] Fetching Behavioral Summary (Graph Aggregate)...")
        resp = await client.get(f"{BASE_URL}/behavior/summary?hours=24")
        print(json.dumps(resp.json(), indent=2))

        # 4. Known Risks
        print("\n[4/6] Checking Loaded Risk Signatures...")
        resp = await client.get(f"{BASE_URL}/risk-files")
        print(json.dumps(resp.json(), indent=2))

        # 5. Trigger AI Analysis (Anomaly Detection)
        print("\n[5/6] Triggering LLM Behavioral Analysis Cycle...")
        print("(This may take a moment as it invokes the LLM provider...)")
        resp = await client.get(f"{BASE_URL}/anomalies")
        print(f"Status: {resp.status_code}")
        print(json.dumps(resp.json(), indent=2))

        # 6. Onboarding Status
        print("\n[6/6] Checking Device Onboarding State...")
        resp = await client.get(f"{BASE_URL}/onboarding/status")
        print(json.dumps(resp.json(), indent=2))

        print("\n--- ✅ POC Workflow Test Complete ---")

if __name__ == "__main__":
    try:
        asyncio.run(test_poc_workflow())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
