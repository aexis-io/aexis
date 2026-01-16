import asyncio
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

from .model import (
    Event, PodStatusUpdate, PodDecision, DecisionContext, Decision,
    Passenger, Cargo, Priority, PodStatus, Route
)
from .message_bus import MessageBus, EventProcessor
from .routing import OfflineRouter
from .ai_provider import AIProvider, AIProviderFactory, MockAIProvider


logger = logging.getLogger(__name__)


class PodDecisionEngine:
    """Hybrid decision engine with AI and fallback routing"""
    
    def __init__(self, pod_id: str, ai_provider: Optional[AIProvider] = None):
        self.pod_id = pod_id
        self.ai_provider = ai_provider or MockAIProvider()  # Default to mock
        self.offline_router = OfflineRouter()
        self.ai_enabled = True
        self.last_ai_failure = None
        self.ai_failure_count = 0
        self.decision_history = []
        
    async def make_decision(self, context: DecisionContext) -> Decision:
        """Make routing decision with AI or fallback"""
        
        # Check if we should use AI
        if self._should_use_ai():
            try:
                decision = await self._ai_decision(context)
                self._record_decision(decision, False)
                return decision
            except Exception as e:
                logger.debug(f"AI decision failed for pod {self.pod_id}: {e}", exc_info=True)
                self._handle_ai_failure()
        
        # Use fallback
        decision = self._fallback_decision(context)
        self._record_decision(decision, True)
        return decision
    
    def _should_use_ai(self) -> bool:
        """Determine if AI should be used based on conditions"""
        
        # Check if AI provider is available
        if not self.ai_provider or not self.ai_provider.is_available():
            logger.debug(f"AI provider {self.ai_provider.get_provider_name() if self.ai_provider else 'None'} not available for pod {self.pod_id}")
            return False
        
        # Check if AI is enabled
        if not self.ai_enabled:
            # Check if we can re-enable AI
            if self.last_ai_failure and \
               datetime.utcnow() - self.last_ai_failure > timedelta(minutes=30):
                self.ai_enabled = True
                self.ai_failure_count = 0
                logger.info(f"Re-enabling AI for pod {self.pod_id}")
            else:
                return False
        
        # Check scenario complexity
        complexity = self._assess_scenario_complexity()
        return complexity > 0.3  # Use AI for moderately complex scenarios
    
    async def _ai_decision(self, context: DecisionContext) -> Decision:
        """Make decision using AI provider"""
        if not self.ai_provider:
            raise create_error(
                ErrorCode.GEMINI_API_KEY_MISSING,
                component="PodDecisionEngine",
                context={"pod_id": self.pod_id}
            )
        
        return await self.ai_provider.make_decision(context)
    
    def _build_ai_prompt(self, context: DecisionContext) -> str:
        """Build comprehensive AI prompt"""
        
        # Format available requests
        requests_text = ""
        for i, req in enumerate(context.available_requests, 1):
            req_type = "Passenger" if req.get('type') == 'passenger' else "Cargo"
            requests_text += f"""
{i}. {req_type} Request:
   - ID: {req.get('id', 'unknown')}
   - From: {req.get('origin', 'unknown')}
   - To: {req.get('destination', 'unknown')}
   - Priority: {req.get('priority', 2)}
   - Weight/Size: {req.get('weight', 0) if req.get('type') == 'cargo' else req.get('group_size', 1)}
   - Special: {req.get('special_needs', []) if req.get('type') == 'passenger' else req.get('hazardous', False)}
"""
        
        # Format network state
        network_text = f"""
Current Network Conditions:
- Congestion Levels: {json.dumps(context.network_state.get('congestion', {}), indent=2)}
- Traffic Flow: {json.dumps(context.network_state.get('traffic', {}), indent=2)}
- Station Status: {json.dumps(context.network_state.get('stations', {}), indent=2)}
"""
        
        prompt = f"""
As Pod {context.pod_id}, analyze this transportation scenario and make optimal routing decisions.

CURRENT STATE:
- Location: {context.current_location}
- Capacity: {context.capacity_available} passengers / {context.weight_available}kg available
- Battery: {context.battery_level:.1%}
- Current Route: {context.current_route}

AVAILABLE REQUESTS:
{requests_text}

NETWORK CONDITIONS:
{network_text}

SYSTEM METRICS:
- Average Wait Time: {context.system_metrics.get('avg_wait_time', 0):.1f} minutes
- System Efficiency: {context.system_metrics.get('efficiency', 0):.1%}
- Active Pods: {context.system_metrics.get('active_pods', 0)}

DECISION REQUIRED:
Provide a JSON response with:
{{
  "accepted_requests": ["request_id1", "request_id2"],
  "rejected_requests": ["request_id3"],
  "route": ["station_a", "station_b", "station_c"],
  "estimated_duration": 25,
  "confidence": 0.85,
  "reasoning": "Brief explanation of decision logic"
}}

OPTIMIZATION CRITERIA:
1. Maximize passenger satisfaction and cargo on-time delivery
2. Minimize total travel time and energy consumption
3. Balance system-wide efficiency with individual pod performance
4. Prioritize high-priority and time-sensitive requests
5. Consider current congestion and traffic conditions

Think step-by-step and provide your decision in the specified JSON format.
"""
        
        return prompt
    
    def _get_system_instruction(self) -> str:
        """Get system instruction with thought signature context"""
        
        base_instruction = """
You are an intelligent transportation pod decision-making system. Your goal is to optimize routing and resource allocation in a decentralized transportation network.

Key Principles:
- Prioritize passenger safety and satisfaction
- Ensure efficient cargo delivery
- Minimize congestion and system delays
- Adapt to changing network conditions
- Learn from previous decisions to improve performance
"""
        
        if self.thought_signature:
            return f"{base_instruction}\n\nPrevious Thought Context:\n{self.thought_signature}"
        
        return base_instruction
    
    def _parse_ai_response(self, response) -> Decision:
        """Parse Gemini AI response into Decision object"""
        try:
            if not response.candidates:
                raise ValueError("No AI response candidates")
            
            content = response.candidates[0].content.parts[0].text if response.candidates[0].content.parts else ""
            
            # Extract JSON from response
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in AI response")
            
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
            
        except Exception as e:
            logger.error(f"Failed to parse AI response: {e}")
            raise
    
    def _fallback_decision(self, context: DecisionContext) -> Decision:
        """Make decision using offline routing algorithm"""
        
        # Use offline router for route optimization
        route_data = self.offline_router.calculate_optimal_route(context)
        
        # Simple request selection based on priority and capacity
        accepted_requests = []
        rejected_requests = []
        capacity_used = 0
        weight_used = 0
        
        for req in context.available_requests:
            if req.get('type') == 'passenger':
                if capacity_used + req.get('group_size', 1) <= context.capacity_available:
                    accepted_requests.append(req.get('id'))
                    capacity_used += req.get('group_size', 1)
                else:
                    rejected_requests.append(req.get('id'))
            elif req.get('type') == 'cargo':
                if weight_used + req.get('weight', 0) <= context.weight_available:
                    accepted_requests.append(req.get('id'))
                    weight_used += req.get('weight', 0)
                else:
                    rejected_requests.append(req.get('id'))
        
        return Decision(
            decision_type="route_selection",
            accepted_requests=accepted_requests,
            rejected_requests=rejected_requests,
            route=route_data.get('route', []),
            estimated_duration=route_data.get('duration', 0),
            confidence=0.75,  # Fixed confidence for fallback
            reasoning=f"Offline routing algorithm - selected {len(accepted_requests)} requests",
            fallback_used=True
        )
    
    def _assess_scenario_complexity(self) -> float:
        """Assess complexity of current scenario (0.0-1.0)"""
        # Simple heuristic based on recent decisions
        if not self.decision_history:
            return 0.5  # Default complexity
        
        recent_decisions = self.decision_history[-5:]  # Last 5 decisions
        
        # Factors that increase complexity:
        # - High rejection rate (conflicting requests)
        # - Variable route lengths (network complexity)
        # - Low confidence (uncertainty)
        
        rejection_rate = sum(1 for d in recent_decisions if len(d.rejected_requests) > 0) / len(recent_decisions)
        route_variance = len(set(tuple(d.route) for d in recent_decisions)) / len(recent_decisions)
        avg_confidence = sum(d.confidence for d in recent_decisions) / len(recent_decisions)
        
        complexity = (rejection_rate * 0.4 + route_variance * 0.3 + (1 - avg_confidence) * 0.3)
        
        return min(1.0, complexity)
    
    def _handle_ai_failure(self):
        """Handle AI decision failure"""
        self.ai_enabled = False
        self.last_ai_failure = datetime.utcnow()
        self.ai_failure_count += 1
        
        # Exponential backoff for re-enabling
        backoff_minutes = min(30, 5 * (2 ** self.ai_failure_count))
        
        logger.warning(
            f"Pod {self.pod_id} AI disabled (failure #{self.ai_failure_count}), "
            f"retry in {backoff_minutes} minutes"
        )
    
    def _record_decision(self, decision: Decision, was_fallback: bool):
        """Record decision for learning and analysis"""
        decision.timestamp = datetime.utcnow()
        self.decision_history.append(decision)
        
        # Keep only recent decisions
        if len(self.decision_history) > 100:
            self.decision_history = self.decision_history[-50:]
        
        logger.info(
            f"Pod {self.pod_id} decision: {len(decision.accepted_requests)} accepted, "
            f"route {len(decision.route)} stops, confidence {decision.confidence:.2f}, "
            f"fallback: {was_fallback}"
        )


class Pod(EventProcessor):
    """Autonomous pod with hybrid decision-making"""
    
    def __init__(self, message_bus: MessageBus, pod_id: str, ai_provider: Optional[AIProvider] = None):
        super().__init__(message_bus, pod_id)
        self.pod_id = pod_id
        self.status = PodStatus.IDLE
        self.location = "station_001"  # Default starting location
        self.capacity_total = 10
        self.capacity_used = 0
        self.weight_total = 500.0
        self.weight_used = 0.0
        self.battery_level = 1.0
        self.current_route = []
        self.passengers = []  # Currently loaded passengers
        self.cargo = []  # Currently loaded cargo
        
        # Decision engine with AI provider
        self.decision_engine = PodDecisionEngine(pod_id, ai_provider)
        
        # Movement tracking
        self.movement_start_time = None
        self.estimated_arrival = None
        
    async def _setup_subscriptions(self):
        """Subscribe to relevant channels"""
        self.message_bus.subscribe(
            MessageBus.CHANNELS['POD_COMMANDS'],
            self._handle_command
        )
        self.message_bus.subscribe(
            MessageBus.CHANNELS['SYSTEM_EVENTS'],
            self._handle_system_event
        )
    
    async def _cleanup_subscriptions(self):
        """Unsubscribe from channels"""
        self.message_bus.unsubscribe(
            MessageBus.CHANNELS['POD_COMMANDS'],
            self._handle_command
        )
        self.message_bus.unsubscribe(
            MessageBus.CHANNELS['SYSTEM_EVENTS'],
            self._handle_system_event
        )
    
    async def _handle_command(self, data: Dict):
        """Handle incoming commands"""
        try:
            command_type = data.get('message', {}).get('command_type', '')
            target = data.get('message', {}).get('target', '')
            
            if target != self.pod_id:
                return
            
            if command_type == 'AssignRoute':
                await self._handle_route_assignment(data)
            
        except Exception as e:
            logger.debug(f"Pod {self.pod_id} command handling error: {e}", exc_info=True)
    
    async def _handle_system_event(self, data: Dict):
        """Handle system-wide events"""
        try:
            event_type = data.get('message', {}).get('event_type', '')
            
            # React to congestion alerts
            if event_type == 'CongestionAlert':
                await self._handle_congestion_alert(data)
                
        except Exception as e:
            logger.debug(f"Pod {self.pod_id} event handling error: {e}", exc_info=True)
    
    async def _handle_route_assignment(self, data: Dict):
        """Handle route assignment command"""
        try:
            parameters = data.get('message', {}).get('parameters', {})
            route = parameters.get('route', [])
            
            if route:
                self.current_route = route
                self.status = PodStatus.EN_ROUTE
                self.movement_start_time = datetime.utcnow()
                
                # Estimate arrival time (simplified)
                self.estimated_arrival = self.movement_start_time + timedelta(minutes=len(route) * 5)
                
                await self._publish_status_update()
                logger.info(f"Pod {self.pod_id} assigned route: {route}")
                
        except Exception as e:
            logger.debug(f"Pod {self.pod_id} route assignment error: {e}", exc_info=True)
    
    async def _handle_congestion_alert(self, data: Dict):
        """Handle congestion alerts"""
        try:
            alert_data = data.get('message', {}).get('data', {})
            affected_routes = alert_data.get('affected_routes', [])
            
            # Check if current route is affected
            current_route_str = "->".join(self.current_route)
            if any(route in current_route_str for route in affected_routes):
                logger.info(f"Pod {self.pod_id} route affected by congestion")
                # Could trigger re-routing decision here
                
        except Exception as e:
            logger.debug(f"Pod {self.pod_id} congestion handling error: {e}", exc_info=True)
    
    async def make_decision(self):
        """Make routing decision"""
        try:
            # Build decision context
            context = await self._build_decision_context()
            
            # Get decision from hybrid engine
            decision = await self.decision_engine.make_decision(context)
            
            # Execute decision
            await self._execute_decision(decision)
            
            # Publish decision event
            await self._publish_decision_event(decision)
            
        except Exception as e:
            logger.debug(f"Pod {self.pod_id} decision making error: {e}", exc_info=True)
    
    async def _build_decision_context(self) -> DecisionContext:
        """Build context for decision making"""
        # This would normally gather real-time data
        # For now, return mock context
        return DecisionContext(
            pod_id=self.pod_id,
            current_location=self.location,
            current_route=self.current_route,
            capacity_available=self.capacity_total - self.capacity_used,
            weight_available=self.weight_total - self.weight_used,
            battery_level=self.battery_level,
            available_requests=[],  # Would be populated from system state
            network_state={},  # Would be populated from system state
            system_metrics={}  # Would be populated from system state
        )
    
    async def _execute_decision(self, decision: Decision):
        """Execute the routing decision"""
        if decision.route:
            self.current_route = decision.route
            self.status = PodStatus.EN_ROUTE
            self.movement_start_time = datetime.utcnow()
            
            # Update capacity based on accepted requests
            # This would be more sophisticated in real implementation
            logger.info(f"Pod {self.pod_id} executing decision: {decision.route}")
    
    async def _publish_decision_event(self, decision: Decision):
        """Publish pod decision event"""
        event = PodDecision(
            pod_id=self.pod_id,
            decision_type=decision.decision_type,
            decision={
                'accepted_requests': decision.accepted_requests,
                'rejected_requests': decision.rejected_requests,
                'route': decision.route,
                'estimated_duration': decision.estimated_duration,
                'confidence': decision.confidence
            },
            reasoning=decision.reasoning,
            confidence=decision.confidence,
            fallback_used=decision.fallback_used
        )
        
        await self.publish_event(event)
    
    async def _publish_status_update(self):
        """Publish pod status update"""
        event = PodStatusUpdate(
            pod_id=self.pod_id,
            location=self.location,
            status=self.status,
            capacity_used=self.capacity_used,
            capacity_total=self.capacity_total,
            weight_used=self.weight_used,
            weight_total=self.weight_total,
            battery_level=self.battery_level,
            current_route=self.current_route
        )
        
        await self.publish_event(event)
    
    def get_state(self) -> Dict:
        """Get current pod state"""
        return {
            'pod_id': self.pod_id,
            'status': self.status.value,
            'location': self.location,
            'capacity': {
                'used': self.capacity_used,
                'total': self.capacity_total
            },
            'weight': {
                'used': self.weight_used,
                'total': self.weight_total
            },
            'battery_level': self.battery_level,
            'current_route': self.current_route,
            'estimated_arrival': self.estimated_arrival.isoformat() if self.estimated_arrival else None,
            'passengers_count': len(self.passengers),
            'cargo_count': len(self.cargo)
        }
