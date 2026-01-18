

import asyncio
import logging
import os
import sys

from core.system import AexisSystem
from web.server import WebServer


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
        logger.error("Please set up your .env file with required variables")
        return
    
    # Create and start system
    system = AexisSystem()
    
    try:
        # Initialize core system
        if not await system.initialize():
            logger.error("Failed to initialize AEXIS system")
            return
        
        # Start web server if enabled
        web_server = None
        if os.getenv('ENABLE_WEB_SERVER', 'true').lower() == 'true':
            web_server = WebServer()
            if not await web_server.initialize(system):
                logger.warning("Failed to initialize web server, continuing without UI")
                web_server = None
        
        # Start core system
        system_task = asyncio.create_task(system.start())
        
        # Start web server if available
        web_task = None
        if web_server:
            web_host = os.getenv('UI_HOST', '0.0.0.0')
            web_port = int(os.getenv('UI_PORT', '8000'))
            web_task = asyncio.create_task(web_server.start(web_host, web_port))
        
        # Wait for tasks
        tasks = [system_task]
        if web_task:
            tasks.append(web_task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
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
