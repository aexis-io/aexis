import asyncio
import json
import logging
import sys
from collections.abc import Callable

import redis.asyncio as redis
from redis.asyncio import Redis

from .errors import ErrorCode, create_error, handle_exception
from .model import Command, Event

logging.basicConfig(
    level=logging.WARN,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("aexis_core.messaging.log"),
    ],
)
logger = logging.getLogger(__name__)


class MessageBus:
    """Redis-based message bus for event-driven communication"""

    def __init__(
        self, redis_url: str = "redis://localhost:6379", password: str | None = None
    ):
        self.redis_url = redis_url
        self.password = password
        self.redis_client: Redis | None = None
        self.pubsub = None
        self.subscribers: dict[str, list[Callable]] = {}
        self.running = False

    async def connect(self) -> bool:
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                password=self.password,
                decode_responses=True,
                socket_connect_timeout=10,
                socket_timeout=5,
                retry_on_timeout=True,
            )

            # Test connection

            await self.redis_client.ping()

            # Create pubsub for subscription handling
            self.pubsub = self.redis_client.pubsub()

            logger.info("Connected to Redis message bus")
            return True

        except redis.AuthenticationError as e:
            error = create_error(
                ErrorCode.REDIS_AUTHENTICATION_FAILED,
                component="MessageBus",
                context={"redis_url": self.redis_url, "original_error": str(e)},
            )
            logger.error(error.message)
            return False

        except redis.ConnectionError as e:
            error = create_error(
                ErrorCode.REDIS_CONNECTION_FAILED,
                component="MessageBus",
                context={"redis_url": self.redis_url, "original_error": str(e)},
            )
            logger.error(error.message)
            return False

        except Exception as e:
            error_details = handle_exception(e, "MessageBus")
            logger.error(
                f"Unexpected error connecting to Redis: {error_details.message}"
            )
            return False

    async def disconnect(self):
        """Close Redis connection"""
        try:
            if self.pubsub:
                await self.pubsub.aclose()
            if self.redis_client:
                await self.redis_client.aclose()
            self.running = False
            logger.info("Disconnected from Redis message bus")
        except Exception as e:
            error_details = handle_exception(e, "MessageBus")
            logger.error(f"Error during disconnect: {error_details.message}")

    async def publish_event(self, channel: str, event: Event) -> bool:
        """Publish event to Redis channel"""
        try:
            if not self.redis_client:
                raise create_error(
                    ErrorCode.REDIS_CONNECTION_FAILED,
                    component="MessageBus",
                    context={"operation": "publish_event"},
                )

            # Validate event
            if not event.event_type or not event.event_id:
                raise create_error(
                    ErrorCode.EVENT_VALIDATION_FAILED,
                    component="MessageBus",
                    context={
                        "event_type": event.event_type,
                        "event_id": event.event_id,
                    },
                )

            # Serialize the entire event dataclass, not just event.data
            from dataclasses import asdict

            event_dict = asdict(event)
            # Convert datetime to ISO string
            # if "timestamp" in event_dict:
            #     event_dict["timestamp"] = event.timestamp.isoformat()
            # print(f"Publishing event to {channel}: {event_dict}")
            message = {"channel": channel, "message": event_dict}

            await self.redis_client.publish(channel, json.dumps(message))
            return True

        except redis.ConnectionError as e:
            error = create_error(
                ErrorCode.REDIS_PUBLISH_FAILED,
                component="MessageBus",
                context={
                    "channel": channel,
                    "event_type": event.event_type,
                    "original_error": str(e),
                },
            )
            logger.error(error.message)
            return False

        except (ValueError, TypeError) as e:
            error = create_error(
                ErrorCode.EVENT_DATA_INVALID,
                component="MessageBus",
                context={"event_type": event.event_type, "original_error": str(e)},
            )
            logger.error(error.message)
            # import traceback
            # traceback.print_exc()
            return False

        except Exception as e:
            error_details = handle_exception(e, "MessageBus")
            logger.error(f"Unexpected error publishing event: {error_details.message}")
            return False

    async def publish_command(self, channel: str, command: Command) -> bool:
        """Publish command to Redis channel"""
        try:
            if not self.redis_client:
                raise create_error(
                    ErrorCode.REDIS_CONNECTION_FAILED,
                    component="MessageBus",
                    context={"operation": "publish_command"},
                )

            # Validate command
            if not command.command_type or not command.target:
                raise create_error(
                    ErrorCode.EVENT_VALIDATION_FAILED,
                    component="MessageBus",
                    context={
                        "command_type": command.command_type,
                        "target": command.target,
                    },
                )

            message = {
                "channel": channel,
                "message": {
                    "command_id": command.command_id,
                    "command_type": command.command_type,
                    "target": command.target,
                    "timestamp": command.timestamp.isoformat(),
                    "parameters": command.parameters,
                },
            }

            await self.redis_client.publish(channel, json.dumps(message))
            logger.debug(f"Published {command.command_type} to {channel}")
            return True

        except redis.ConnectionError as e:
            error = create_error(
                ErrorCode.REDIS_PUBLISH_FAILED,
                component="MessageBus",
                context={
                    "channel": channel,
                    "command_type": command.command_type,
                    "original_error": str(e),
                },
            )
            logger.error(error.message)
            return False

        except json.JSONEncodeError as e:
            error = create_error(
                ErrorCode.EVENT_DATA_INVALID,
                component="MessageBus",
                context={
                    "command_type": command.command_type,
                    "original_error": str(e),
                },
            )
            logger.error(error.message)
            return False

        except Exception as e:
            error_details = handle_exception(e, "MessageBus")
            logger.error(
                f"Unexpected error publishing command: {error_details.message}"
            )
            return False

    def subscribe(self, channel: str, handler: Callable):
        """Subscribe to channel with event handler"""
        try:
            if not callable(handler):
                raise create_error(
                    ErrorCode.EVENT_VALIDATION_FAILED,
                    component="MessageBus",
                    context={
                        "channel": channel,
                        "handler_type": type(handler).__name__,
                    },
                )

            if channel not in self.subscribers:
                self.subscribers[channel] = []
                # If already running, we need to subscribe in Redis too
                if self.running and self.pubsub:
                    asyncio.create_task(self.pubsub.subscribe(channel))
                    logger.info(f"Dynamically subscribed to Redis channel: {channel}")

            self.subscribers[channel].append(handler)
            logger.debug(f"Subscribed handler to {channel}")

        except Exception as e:
            error_details = handle_exception(e, "MessageBus")
            logger.error(
                f"Error subscribing to channel {channel}: {error_details.message}"
            )

    def unsubscribe(self, channel: str, handler: Callable):
        """Unsubscribe handler from channel"""
        try:
            if channel in self.subscribers:
                try:
                    self.subscribers[channel].remove(handler)
                    logger.debug(f"Unsubscribed handler from {channel}")
                except ValueError:
                    logger.warning(
                        f"Handler not found in channel {channel} subscribers"
                    )
        except Exception as e:
            error_details = handle_exception(e, "MessageBus")
            logger.error(
                f"Error unsubscribing from channel {channel}: {error_details.message}"
            )

    async def start_listening(self):
        """Start listening for subscribed channels"""
        try:
            if not self.pubsub:
                raise create_error(
                    ErrorCode.REDIS_CONNECTION_FAILED,
                    component="MessageBus",
                    context={"operation": "start_listening"},
                )

            # Subscribe to all channels
            for channel in list(self.subscribers.keys()):
                try:
                    await self.pubsub.subscribe(channel)
                    logger.info(f"Subscribed to Redis channel: {channel}")
                except redis.ConnectionError as e:
                    error = create_error(
                        ErrorCode.REDIS_SUBSCRIBE_FAILED,
                        component="MessageBus",
                        context={"channel": channel, "original_error": str(e)},
                    )
                    logger.error(error.message)
                    continue

            self.running = True

            # Listen for messages
            async for message in self.pubsub.listen():
                if not self.running:
                    break

                if message["type"] == "message":
                    await self._handle_message(message)

        except Exception as e:
            error_details = handle_exception(e, "MessageBus")
            logger.error(f"Error in message listening loop: {error_details.message}")
            self.running = False

    async def _handle_message(self, message):
        """Handle incoming Redis message"""
        try:
            channel = message["channel"]

            # Validate channel has subscribers
            if channel not in self.subscribers:
                logger.warning(f"Received message on unsubscribed channel: {channel}")
                return

            # Parse message data
            try:
                data = json.loads(message["data"])
            except json.JSONDecodeError as e:
                error = create_error(
                    ErrorCode.EVENT_DATA_INVALID,
                    component="MessageBus",
                    context={"channel": channel, "original_error": str(e)},
                )
                logger.error(error.message)
                return

            # Call all subscribers for this channel
            for handler in list(self.subscribers[channel]):
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception as e:
                    error_details = handle_exception(e, f"Handler-{channel}")
                    logger.error(f"Handler error on {channel}: {error_details.message}")

        except Exception as e:
            error_details = handle_exception(e, "MessageBus")
            logger.error(f"Failed to handle message: {error_details.message}")

    async def stop_listening(self):
        """Stop listening for messages"""
        try:
            self.running = False
            if self.pubsub:
                await self.pubsub.unsubscribe()
                await self.pubsub.aclose()
            logger.info("Stopped listening to Redis channels")
        except Exception as e:
            error_details = handle_exception(e, "MessageBus")
            logger.error(f"Error stopping message listening: {error_details.message}")

    # Channel constants
    CHANNELS = {
        "PASSENGER_EVENTS": "aexis:events:passenger",
        "CARGO_EVENTS": "aexis:events:cargo",
        "POD_EVENTS": "aexis:events:pods",
        "SYSTEM_EVENTS": "aexis:events:system",
        "CONGESTION_EVENTS": "aexis:events:congestion",
        "POD_COMMANDS": "aexis:commands:pods",
        "STATION_COMMANDS": "aexis:commands:stations",
        "SYSTEM_COMMANDS": "aexis:commands:system",
    }

    @classmethod
    def get_event_channel(cls, event_type: str) -> str:
        """Get appropriate channel for event type"""
        try:
            if "passenger" in event_type.lower():
                return cls.CHANNELS["PASSENGER_EVENTS"]
            elif "cargo" in event_type.lower():
                return cls.CHANNELS["CARGO_EVENTS"]
            elif "pod" in event_type.lower():
                return cls.CHANNELS["POD_EVENTS"]
            elif "congestion" in event_type.lower():
                return cls.CHANNELS["CONGESTION_EVENTS"]
            else:
                return cls.CHANNELS["SYSTEM_EVENTS"]
        except Exception as e:
            logger.error(f"Error determining event channel for {event_type}: {e}")
            return cls.CHANNELS["SYSTEM_EVENTS"]

    @classmethod
    def get_command_channel(cls, command_type: str, target_type: str) -> str:
        """Get appropriate channel for command type"""
        try:
            if target_type == "pod":
                return cls.CHANNELS["POD_COMMANDS"]
            elif target_type == "station":
                return cls.CHANNELS["STATION_COMMANDS"]
            else:
                return cls.CHANNELS["SYSTEM_COMMANDS"]
        except Exception as e:
            logger.error(f"Error determining command channel for {command_type}: {e}")
            return cls.CHANNELS["SYSTEM_COMMANDS"]


class LocalMessageBus(MessageBus):
    """In-memory message bus for testing and local operation (No Redis required)"""

    def __init__(self):
        super().__init__(redis_url="local://")
        self.subscribers: dict[str, list[Callable]] = {}
        self.running = False

    async def connect(self) -> bool:
        """Simulate connection"""
        self.running = True
        logger.info("Local message bus initialized")
        return True

    async def disconnect(self):
        """Simulate disconnect"""
        self.running = False
        logger.info("Local message bus disconnected")

    async def publish_event(self, channel: str, event: Event) -> bool:
        """Publish event directly to local handlers"""
        if not self.running:
            return False

        from dataclasses import asdict
        event_dict = asdict(event)
        if "timestamp" in event_dict:
            ts = event.timestamp
            event_dict["timestamp"] = ts if isinstance(ts, str) else ts.isoformat()

        message = {"channel": channel, "message": event_dict}
        
        # Immediate dispatch in local bus
        await self._handle_local_message(channel, message)
        return True

    async def publish_command(self, channel: str, command: Command) -> bool:
        """Publish command directly to local handlers"""
        if not self.running:
            return False

        message = {
            "channel": channel,
            "message": {
                "command_id": command.command_id,
                "command_type": command.command_type,
                "target": command.target,
                "timestamp": command.timestamp.isoformat(),
                "parameters": command.parameters,
            },
        }
        
        # Immediate dispatch in local bus
        await self._handle_local_message(channel, message)
        return True

    def subscribe(self, channel: str, handler: Callable):
        """Subscribe to local channel"""
        if channel not in self.subscribers:
            self.subscribers[channel] = []
        self.subscribers[channel].append(handler)

    def unsubscribe(self, channel: str, handler: Callable):
        """Unsubscribe from local channel"""
        if channel in self.subscribers:
            try:
                self.subscribers[channel].remove(handler)
            except ValueError:
                pass

    async def start_listening(self):
        """No-op for local bus (dispatch is immediate)"""
        self.running = True

    async def _handle_local_message(self, channel: str, data: dict):
        """Dispatch message to local handlers"""
        if channel not in self.subscribers:
            return

        for handler in self.subscribers[channel]:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Local handler error on {channel}: {e}")

    async def stop_listening(self):
        """Stop local bus"""
        self.running = False


class EventProcessor:
    """Base class for event processors"""

    def __init__(self, message_bus: MessageBus, component_id: str):
        self.message_bus = message_bus
        self.component_id = component_id
        self.processing = False

    async def start(self):
        """Start processing events"""
        try:
            self.processing = True
            await self._setup_subscriptions()
            logger.info(f"Started event processor for {self.component_id}")
        except Exception as e:
            error_details = handle_exception(e, self.component_id)
            logger.error(f"Failed to start event processor: {error_details.message}")
            raise

    async def stop(self):
        """Stop processing events"""
        try:
            self.processing = False
            await self._cleanup_subscriptions()
            logger.info(f"Stopped event processor for {self.component_id}")
        except Exception as e:
            error_details = handle_exception(e, self.component_id)
            logger.error(f"Failed to stop event processor: {error_details.message}")

    async def _setup_subscriptions(self):
        """Override to setup channel subscriptions"""
        pass

    async def _cleanup_subscriptions(self):
        """Override to cleanup channel subscriptions"""
        pass

    async def publish_event(self, event: Event):
        """Publish event with component source"""
        try:
            event.source = self.component_id
            channel = MessageBus.get_event_channel(event.event_type)
            await self.message_bus.publish_event(channel, event)
        except Exception as e:
            error_details = handle_exception(e, self.component_id)
            logger.error(f"Failed to publish event: {error_details.message}")
            raise

    async def publish_command(self, command: Command):
        """Publish command"""
        try:
            channel = MessageBus.get_command_channel(
                command.command_type, self._get_target_type(command.target)
            )
            await self.message_bus.publish_command(channel, command)
        except Exception as e:
            error_details = handle_exception(e, self.component_id)
            logger.error(f"Failed to publish command: {error_details.message}")
            raise

    def _get_target_type(self, target: str) -> str:
        """Determine target type from ID"""
        try:
            if target.startswith("pod_"):
                return "pod"
            elif target.startswith("station_"):
                return "station"
            else:
                return "system"
        except Exception as e:
            logger.error(f"Error determining target type for {target}: {e}")
            return "system"
