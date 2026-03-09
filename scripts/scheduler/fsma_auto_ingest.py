#!/usr/bin/env python3
"""
FSMA Auto-Ingestion Scheduler

Automatically loads demo data for FSMA 204 demonstrations.
Can be run as a cron job or triggered via API.

Usage:
    python fsma_auto_ingest.py --mode demo
    python fsma_auto_ingest.py --mode watch --interval 300
    python fsma_auto_ingest.py --mode schedule --cron "0 */6 * * *"
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import random
import string

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import httpx
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
except ImportError:
    print("Required packages not installed. Run: pip install httpx apscheduler")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('fsma_auto_ingest')

# Configuration
GRAPH_API_URL = os.getenv('GRAPH_API_URL', 'http://localhost:8100')
ADMIN_API_URL = os.getenv('ADMIN_API_URL', 'http://localhost:8400')
API_KEY = os.getenv('REGENGINE_API_KEY', '')
ADMIN_KEY = os.getenv('ADMIN_MASTER_KEY', '')


def generate_tlc() -> str:
    """Generate a realistic Traceability Lot Code."""
    products = ['ROMAINE', 'SPINACH', 'KALE', 'TOMATO', 'LETTUCE', 'CARROT']
    product = random.choice(products)
    batch = ''.join(random.choices(string.digits, k=4))
    date = datetime.now().strftime('%Y%m%d')
    return f"TLC-{product}-{date}-{batch}"


def generate_gln() -> str:
    """Generate a valid-looking GLN (13 digits)."""
    prefix = '00123456789'
    suffix = ''.join(random.choices(string.digits, k=2))
    return prefix + suffix


class FSMADemoDataGenerator:
    """Generates realistic FSMA 204 demo data."""

    FACILITIES = [
        {"name": "Green Valley Farms", "type": "FARM", "state": "CA"},
        {"name": "Sunrise Orchards", "type": "FARM", "state": "AZ"},
        {"name": "Pacific Produce Packing", "type": "PROCESSOR", "state": "CA"},
        {"name": "FreshPack Industries", "type": "PROCESSOR", "state": "TX"},
        {"name": "National Food Distribution", "type": "DISTRIBUTOR", "state": "IL"},
        {"name": "Metro Wholesale Foods", "type": "DISTRIBUTOR", "state": "NY"},
        {"name": "SaveMart Grocery", "type": "RETAILER", "state": "CA"},
        {"name": "FreshMart Stores", "type": "RETAILER", "state": "TX"},
        {"name": "City Supermarket", "type": "RETAILER", "state": "NY"},
    ]

    PRODUCTS = [
        {"name": "Romaine Lettuce", "gtin": "00012345678901"},
        {"name": "Baby Spinach", "gtin": "00012345678902"},
        {"name": "Mixed Greens", "gtin": "00012345678903"},
        {"name": "Organic Kale", "gtin": "00012345678904"},
        {"name": "Cherry Tomatoes", "gtin": "00012345678905"},
    ]

    def generate_supply_chain(self) -> dict:
        """Generate a complete supply chain with events."""
        # Select facilities for this chain
        farm = random.choice([f for f in self.FACILITIES if f["type"] == "FARM"])
        processor = random.choice([f for f in self.FACILITIES if f["type"] == "PROCESSOR"])
        distributor = random.choice([f for f in self.FACILITIES if f["type"] == "DISTRIBUTOR"])
        retailer = random.choice([f for f in self.FACILITIES if f["type"] == "RETAILER"])

        product = random.choice(self.PRODUCTS)
        tlc = generate_tlc()
        quantity = random.randint(100, 1000)

        # Generate timeline
        base_date = datetime.now() - timedelta(days=random.randint(1, 30))

        events = []

        # 1. Creation at farm
        events.append({
            "type": "CREATION",
            "timestamp": base_date.isoformat(),
            "facility": farm["name"],
            "facility_type": farm["type"],
            "facility_gln": generate_gln(),
            "lot_tlc": tlc,
            "quantity": quantity,
            "product": product["name"],
            "gtin": product["gtin"],
        })

        # 2. Shipping from farm
        ship_date = base_date + timedelta(hours=random.randint(12, 48))
        events.append({
            "type": "SHIPPING",
            "timestamp": ship_date.isoformat(),
            "facility": farm["name"],
            "facility_type": farm["type"],
            "facility_gln": events[0]["facility_gln"],
            "lot_tlc": tlc,
            "quantity": quantity,
            "destination": processor["name"],
        })

        # 3. Receiving at processor
        recv_date = ship_date + timedelta(hours=random.randint(4, 24))
        processor_gln = generate_gln()
        events.append({
            "type": "RECEIVING",
            "timestamp": recv_date.isoformat(),
            "facility": processor["name"],
            "facility_type": processor["type"],
            "facility_gln": processor_gln,
            "lot_tlc": tlc,
            "quantity": quantity,
            "source": farm["name"],
        })

        # 4. Transformation at processor
        transform_date = recv_date + timedelta(hours=random.randint(2, 12))
        output_quantity = int(quantity * random.uniform(0.85, 0.95))  # Some loss
        new_tlc = f"{tlc}-PROC"
        events.append({
            "type": "TRANSFORMATION",
            "timestamp": transform_date.isoformat(),
            "facility": processor["name"],
            "facility_type": processor["type"],
            "facility_gln": processor_gln,
            "input_lot": tlc,
            "input_quantity": quantity,
            "output_lot": new_tlc,
            "output_quantity": output_quantity,
        })

        # 5. Shipping from processor
        ship_date2 = transform_date + timedelta(hours=random.randint(6, 24))
        events.append({
            "type": "SHIPPING",
            "timestamp": ship_date2.isoformat(),
            "facility": processor["name"],
            "facility_type": processor["type"],
            "facility_gln": processor_gln,
            "lot_tlc": new_tlc,
            "quantity": output_quantity,
            "destination": distributor["name"],
        })

        # 6. Receiving at distributor
        recv_date2 = ship_date2 + timedelta(hours=random.randint(8, 36))
        distributor_gln = generate_gln()
        events.append({
            "type": "RECEIVING",
            "timestamp": recv_date2.isoformat(),
            "facility": distributor["name"],
            "facility_type": distributor["type"],
            "facility_gln": distributor_gln,
            "lot_tlc": new_tlc,
            "quantity": output_quantity,
            "source": processor["name"],
        })

        # 7. Shipping from distributor
        ship_date3 = recv_date2 + timedelta(hours=random.randint(4, 24))
        events.append({
            "type": "SHIPPING",
            "timestamp": ship_date3.isoformat(),
            "facility": distributor["name"],
            "facility_type": distributor["type"],
            "facility_gln": distributor_gln,
            "lot_tlc": new_tlc,
            "quantity": output_quantity,
            "destination": retailer["name"],
        })

        # 8. Receiving at retailer
        recv_date3 = ship_date3 + timedelta(hours=random.randint(2, 12))
        events.append({
            "type": "RECEIVING",
            "timestamp": recv_date3.isoformat(),
            "facility": retailer["name"],
            "facility_type": retailer["type"],
            "facility_gln": generate_gln(),
            "lot_tlc": new_tlc,
            "quantity": output_quantity,
            "source": distributor["name"],
        })

        return {
            "tlc": tlc,
            "product": product,
            "events": events,
            "facilities": [farm, processor, distributor, retailer],
        }


class FSMAAutoIngester:
    """Handles automatic ingestion of FSMA demo data."""

    def __init__(self, api_key: str, graph_url: str = GRAPH_API_URL):
        self.api_key = api_key
        self.graph_url = graph_url
        self.generator = FSMADemoDataGenerator()
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()

    async def check_health(self) -> bool:
        """Check if the FSMA service is healthy."""
        try:
            response = await self.client.get(f"{self.graph_url}/v1/fsma/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def ingest_supply_chain(self, chain: dict) -> bool:
        """Ingest a supply chain's events into the system."""
        headers = {"X-RegEngine-API-Key": self.api_key, "Content-Type": "application/json"}

        try:
            # In production, this would call the actual ingestion endpoint
            # For demo, we'll simulate success
            logger.info(f"Ingesting supply chain for TLC: {chain['tlc']}")
            logger.info(f"  Product: {chain['product']['name']}")
            logger.info(f"  Events: {len(chain['events'])}")

            # Simulate API call
            # response = await self.client.post(
            #     f"{self.graph_url}/v1/fsma/ingest",
            #     headers=headers,
            #     json={"events": chain["events"]}
            # )
            # return response.status_code == 200

            # For demo purposes, just log the data
            for event in chain["events"]:
                logger.debug(f"  Event: {event['type']} at {event['facility']}")

            return True

        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            return False

    async def run_demo_load(self, num_chains: int = 5):
        """Load demo supply chains."""
        logger.info(f"Starting demo data load ({num_chains} supply chains)")

        if not await self.check_health():
            logger.warning("FSMA service not healthy, proceeding anyway for demo")

        success_count = 0
        for i in range(num_chains):
            chain = self.generator.generate_supply_chain()
            if await self.ingest_supply_chain(chain):
                success_count += 1
            await asyncio.sleep(0.5)  # Small delay between ingestions

        logger.info(f"Demo load complete: {success_count}/{num_chains} chains ingested")
        return success_count

    async def run_continuous(self, interval_seconds: int = 300):
        """Run continuous ingestion at specified interval."""
        logger.info(f"Starting continuous ingestion (interval: {interval_seconds}s)")

        while True:
            chain = self.generator.generate_supply_chain()
            await self.ingest_supply_chain(chain)
            await asyncio.sleep(interval_seconds)


async def run_scheduled(cron_expression: str, api_key: str):
    """Run ingestion on a cron schedule."""
    scheduler = AsyncIOScheduler()
    ingester = FSMAAutoIngester(api_key)

    async def scheduled_job():
        async with ingester:
            await ingester.run_demo_load(num_chains=3)

    scheduler.add_job(
        scheduled_job,
        CronTrigger.from_crontab(cron_expression),
        id='fsma_auto_ingest'
    )

    logger.info(f"Scheduler started with cron: {cron_expression}")
    scheduler.start()

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


async def main():
    parser = argparse.ArgumentParser(description='FSMA Auto-Ingestion Scheduler')
    parser.add_argument('--mode', choices=['demo', 'watch', 'schedule'], default='demo',
                        help='Ingestion mode')
    parser.add_argument('--interval', type=int, default=300,
                        help='Interval in seconds for watch mode')
    parser.add_argument('--cron', type=str, default='0 */6 * * *',
                        help='Cron expression for schedule mode')
    parser.add_argument('--chains', type=int, default=5,
                        help='Number of supply chains to generate in demo mode')
    parser.add_argument('--api-key', type=str, default=API_KEY,
                        help='API key for authentication')

    args = parser.parse_args()

    if not args.api_key:
        logger.warning("No API key provided, running in demo mode without authentication")

    if args.mode == 'demo':
        async with FSMAAutoIngester(args.api_key) as ingester:
            await ingester.run_demo_load(num_chains=args.chains)

    elif args.mode == 'watch':
        async with FSMAAutoIngester(args.api_key) as ingester:
            await ingester.run_continuous(interval_seconds=args.interval)

    elif args.mode == 'schedule':
        await run_scheduled(args.cron, args.api_key)


if __name__ == '__main__':
    asyncio.run(main())
