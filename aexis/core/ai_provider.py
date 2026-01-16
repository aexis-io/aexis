from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

from .model import DecisionContext, Decision
from .errors import create_error, ErrorCode, handle_exception


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
    
    def __init__(self, client):
        self.client = client
        self.thought_signature = None
        
    async def make_decision(self, context: DecisionContext) -> Decision:
        """Make decision using Gemini 3"""
        try:
            if not self.is_available():
                raise create_error(
                    ErrorCode.GEMINI_API_KEY_MISSING,
                    component="GeminiAIProvider",
                    context={"pod_id": context.pod_id}
                )
            
            prompt = self._build_prompt(context)
            response = await self._call_gemini(prompt)
            decision = self._parse_response(response)
            
            self.thought_signature = response.candidates[0].content if response.candidates else None
            
            return decision
            
        except Exception as e:
            logger.debug(f"Gemini AI decision failed: {e}", exc_info=True)
            raise
    
    def is_available(self) -> bool:
        """Check if Gemini is available"""
        return self.client is not None
    
    def get_provider_name(self) -> str:
        return "Gemini 3"
    
    async def _call_gemini(self, prompt: str):
        """Call Gemini API with proper configuration"""
        from google.genai import types
        
        config = types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=1000,
            system_instruction=self._get_system_instruction()
        )
        
        response = await self.client.aio.models.generate_content(
            model="gemini-3-pro-preview",
            contents=prompt,
            config=config
        )
        
        return response
    
    def _build_prompt(self, context: DecisionContext) -> str:
        """Build comprehensive prompt for decision making"""
        # This would contain the same prompt logic as before
        # but isolated within the Gemini provider
        return f"Analyze transportation scenario for pod {context.pod_id}..."
    
    def _get_system_instruction(self) -> str:
        """Get system instruction with thought signature"""
        base_instruction = "You are an intelligent transportation decision system..."
        
        if self.thought_signature:
            return f"{base_instruction}\n\nPrevious Thought Context:\n{self.thought_signature}"
        
        return base_instruction
    
    def _parse_response(self, response) -> Decision:
        """Parse Gemini response into Decision object"""
        # This would contain the same parsing logic as before
        # but isolated within the Gemini provider
        import json
        
        if not response.candidates:
            raise create_error(
                ErrorCode.GEMINI_RESPONSE_PARSING_FAILED,
                component="GeminiAIProvider",
                context={"reason": "No candidates in response"}
            )
        
        content = response.candidates[0].content.parts[0].text if response.candidates[0].content.parts else ""
        
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        
        if json_start == -1 or json_end == 0:
            raise create_error(
                ErrorCode.GEMINI_RESPONSE_PARSING_FAILED,
                component="GeminiAIProvider",
                context={"reason": "No JSON found in response"}
            )
        
        json_str = content[json_start:json_end]
        data = json.loads(json_str)
        
        return Decision(
            decision_type="route_selection",
            accepted_requests=data.get('accepted_requests', []),
            rejected_requests=data.get('rejected_requests', []),
            route=data.get('route', []),
            estimated_duration=data.get('estimated_duration', 0),
            confidence=data.get('confidence', 0.5),
            reasoning=data.get('reasoning', 'AI decision'),
            fallback_used=False
        )


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
            accepted = [context.available_requests[0].get('id')] if context.available_requests else []
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
            fallback_used=False
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
            client = kwargs.get('client')
            if not client:
                raise create_error(
                    ErrorCode.GEMINI_API_KEY_MISSING,
                    component="AIProviderFactory",
                    context={"provider_type": provider_type}
                )
            return GeminiAIProvider(client, kwargs.get('daily_limit', 100))
        
        elif provider_type.lower() == "mock":
            return MockAIProvider(kwargs.get('response_delay', 0.1))
        
        else:
            raise create_error(
                ErrorCode.CONFIG_INVALID_VALUE,
                component="AIProviderFactory",
                context={"provider_type": provider_type, "supported": ["gemini", "mock"]}
            )
    
    @staticmethod
    def get_available_providers() -> List[str]:
        """Get list of available provider types"""
        return ["gemini", "mock"]
