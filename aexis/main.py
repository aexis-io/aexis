

import asyncio
import logging
import os
import sys

from core.system import AexisSystem


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('aexis.log')
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """Main entry point for AEXIS system"""
    logger.info("Starting AEXIS - Autonomous Event-Driven Transportation Intelligence System")
    
    # Check environment variables
    required_vars = ['REDIS_PASSWORD']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        logger.error("Please set up your .env file with the required variables")
        return
    
    # Create and start system
    system = AexisSystem()
    
    try:
        await system.start()
    except Exception as e:
        logger.debug(f"System failed to start: {e}", exc_info=True)
        await system.shutdown()
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.debug(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
