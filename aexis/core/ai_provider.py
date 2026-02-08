import logging
from abc import ABC, abstractmethod

from .errors import ErrorCode, create_error
from .model import Decision, DecisionContext

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    """Abstract base class for AI decision providers"""

    @abstractmethod
    async def make_decision(self, context: DecisionContext) -> Decision:
        """Make routing decision using AI"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if AI provider is available"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get provider name for logging"""
        pass


class GeminiAIProvider(AIProvider):
    """Gemini 3 AI provider implementation"""

    def __init__(self, client, daily_limit: int = 100):
        self.client = client
        self.daily_limit = daily_limit
        self.call_count = 0
        self.thought_signature = None

    async def make_decision(self, context: DecisionContext) -> Decision:
        """Make decision using Gemini 3"""
        try:
            if not self.is_available():
                raise create_error(
                    ErrorCode.GEMINI_API_KEY_MISSING,
                    component="GeminiAIProvider",
                    context={"pod_id": context.pod_id},
                )

            if self.call_count >= self.daily_limit:
                logger.warning(f"Daily limit reached for Gemini provider ({self.daily_limit})")
                raise create_error(
                    ErrorCode.AI_PROVIDER_LIMIT_REACHED,
                    component="GeminiAIProvider",
                    context={"limit": self.daily_limit},
                )

            prompt = self._build_prompt(context)
            response = await self._call_gemini(prompt)
            decision = self._parse_response(response, context)

            # Update state
            self.call_count += 1
            if response.candidates:
                # Store the thought process for continuity, if available
                # Note: This depends on the specific model response structure
                pass

            return decision

        except Exception as e:
            logger.error(f"Gemini AI decision failed: {e}", exc_info=True)
            raise

    def is_available(self) -> bool:
        """Check if Gemini is available"""
        return self.client is not None

    def get_provider_name(self) -> str:
        return "Gemini 3"

    async def _call_gemini(self, prompt: str):
        """Call Gemini API with proper configuration"""
        from google.genai import types

        # Pydantic-based schema for structured output (if supported) or strict JSON instruction
        # For now, we use a strong system prompt and JSON mode if available, 
        # but the google-genai SDK 0.1+ supports response_mime_type="application/json"
        
        config = types.GenerateContentConfig(
            temperature=0.2,  # Low temperature for deterministic routing
            max_output_tokens=2048,
            system_instruction=self._get_system_instruction(),
            response_mime_type="application/json",
        )

        try:
            import asyncio
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model="gemini-2.0-flash-001",
                    contents=prompt,
                    config=config,
                ),
                timeout=30.0
            ) 
            return response
        except asyncio.TimeoutError:
            logger.error("Gemini API call timed out after 30s")
            raise create_error(
                ErrorCode.AI_PROVIDER_TIMEOUT,
                component="GeminiAIProvider",
                context={"timeout": 30.0}
            )
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise

    def _build_prompt(self, context: DecisionContext) -> str:
        """Build comprehensive prompt for decision making"""
        import json
        
        # Serialize context
        # We need to be careful with datetime objects and non-serializable types
        # Using a helper or manual dict construction
        
        ctx_data = {
            "pod_id": context.pod_id,
            "current_location": context.current_location,
            "capacity": {"available": context.capacity_available},
            "weight": {"available": context.weight_available},
            "passengers": context.passengers if context.passengers else [],
            "cargo": context.cargo if context.cargo else [],
            "requests": context.available_requests,
            "network_status": context.network_state,
        }
        
        return f"""
Analyze the following transportation scenario and make a routing decision.

Context:
{json.dumps(ctx_data, indent=2, default=str)}

Task:
1. Evaluate all available requests against pod constraints (capacity, weight).
2. Optimize for efficiency (time/distance) and priority.
3. Determine which requests to accept and which to reject.
4. Plan a route (sequence of station IDs) to service accepted requests and current payload.
5. Provide a confidence score and reasoning.

Output MUST be a valid JSON object matching the Decision schema.
"""

    def _get_system_instruction(self) -> str:
        """Get system instruction with thought signature"""
        return """
You are the AEXIS Central Routing Intelligence. Your goal is to optimize pod routing for a futuristic hyperloop network.
You must prioritize:
1. Passenger safety and comfort.
2. Delivery deadlines for cargo.
3. System efficiency (minimizing empty travel).

You must output ONLY valid JSON.
The JSON schema is:
{
    "accepted_requests": ["request_id_1", ...],
    "rejected_requests": ["request_id_2", ...],
    "route": ["station_a", "station_b", ...],
    "estimated_duration": <int_minutes>,
    "confidence": <float_0_to_1>,
    "reasoning": "<string_explanation>"
}
Do not include markdown code blocks (```json ... ```) in the output, just the raw JSON string.
"""

    def _parse_response(self, response, context: DecisionContext) -> Decision:
        """Parse Gemini response into Decision object"""
        import json
        
        text = ""
        try:
            if not response.candidates:
                raise ValueError("No candidates returned")
                
            # Extract text
            candidate = response.candidates[0]
            if not candidate.content or not candidate.content.parts:
                 raise ValueError("Empty content in candidate")
                 
            text = candidate.content.parts[0].text
            
            # Clean up potential markdown formatting if the model disregards the "no markdown" instruction
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            data = json.loads(text)
            
            # Validation
            required_fields = ["accepted_requests", "route", "confidence"]
            for field in required_fields:
                if field not in data:
                     raise ValueError(f"Missing required field: {field}")

            return Decision(
                decision_type="route_selection",
                accepted_requests=data.get("accepted_requests", []),
                rejected_requests=data.get("rejected_requests", []),
                route=data.get("route", [context.current_location]),
                estimated_duration=data.get("estimated_duration", 0),
                confidence=float(data.get("confidence", 0.0)),
                reasoning=data.get("reasoning", "Gemini decision"),
                fallback_used=False,
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from Gemini: {e}\nResponse text: {text}")
            raise create_error(
                ErrorCode.GEMINI_RESPONSE_PARSING_FAILED,
                component="GeminiAIProvider",
                context={"error": str(e), "text_snippet": text[:100]}
            )
        except Exception as e:
             logger.error(f"Error parsing Gemini response: {e}")
             raise


class MockAIProvider(AIProvider):
    """Mock AI provider for testing and development"""

    def __init__(self, response_delay: float = 0.1):
        self.response_delay = response_delay
        self.call_count = 0

    async def make_decision(self, context: DecisionContext) -> Decision:
        """Make mock decision"""
        import asyncio

        await asyncio.sleep(self.response_delay)

        self.call_count += 1

        # Simple mock logic
        if context.available_requests:
            accepted = (
                [context.available_requests[0].get("id")]
                if context.available_requests
                else []
            )
        else:
            accepted = []

        return Decision(
            decision_type="route_selection",
            accepted_requests=accepted,
            rejected_requests=[],
            route=[context.current_location],
            estimated_duration=10,
            confidence=0.8,
            reasoning=f"Mock decision #{self.call_count}",
            fallback_used=False,
        )

    def is_available(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return "Mock AI"


class AIProviderFactory:
    """Factory for creating AI providers"""

    @staticmethod
    def create_provider(provider_type: str, **kwargs) -> AIProvider:
        """Create AI provider instance"""
        if provider_type.lower() == "gemini":
            client = kwargs.get("client")
            if not client:
                import os
                from google import genai
                
                api_key = os.environ.get("GEMINI_API_KEY")
                if not api_key:
                    raise create_error(
                        ErrorCode.GEMINI_API_KEY_MISSING,
                        component="AIProviderFactory",
                        context={"provider_type": provider_type},
                    )
                client = genai.Client(api_key=api_key)
                
            return GeminiAIProvider(client, kwargs.get("daily_limit", 100))

        elif provider_type.lower() == "mock":
            return MockAIProvider(kwargs.get("response_delay", 0.1))

        else:
            raise create_error(
                ErrorCode.CONFIG_INVALID_VALUE,
                component="AIProviderFactory",
                context={
                    "provider_type": provider_type,
                    "supported": ["gemini", "mock"],
                },
            )

    @staticmethod
    def get_available_providers() -> list[str]:
        """Get list of available provider types"""
        return ["gemini", "mock"]
