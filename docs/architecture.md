# Architecture Overview

## System Design

AEXIS is an event-driven decentralized transportation system where autonomous pods make intelligent decisions using Gemini 3 AI without central coordination.

## Core Components

### Event System
- **Message Bus**: Redis pub/sub for real-time event distribution
- **Event Types**: Passenger arrivals, cargo requests, pod availability, congestion alerts
- **Decentralized Processing**: Each component reacts to relevant events independently

### Autonomous Pods
- **Decision Engine**: Gemini 3 with Thought Signatures for consistent behavior
- **Multi-Level Reasoning**: Route optimization, capacity assessment, congestion prediction
- **Independent Operation**: No central controller required

### Station Network
- **Dynamic Inflows**: Real-time passenger and cargo arrivals
- **Local Processing**: Station-level event handling and resource management
- **Network Topology**: Configurable connections between stations

## Data Flow

```
Event → Redis Message Bus → Multiple Handlers → Gemini 3 Decisions → Actions
```

1. Events published to Redis channels
2. Multiple subscribers react simultaneously
3. Pods use Gemini 3 for intelligent decisions
4. Actions generate new events (cascade)

## Gemini 3 Integration

### Thought Signatures
- Maintain pod personality and learning across events
- Persistent decision context for consistent behavior
- Enables long-term strategy development

### Multi-Level Thinking
- **Level 1**: Immediate capacity/weight assessments
- **Level 2**: Route optimization considering current conditions
- **Level 3**: System-wide impact prediction and planning

### Real-Time Operation
- Sub-second decision making for transportation logistics
- Optimized prompts for fast Gemini 3 responses
- Fallback logic for critical decisions

## Scalability Design

### Horizontal Scaling
- Add pods/stations without system redesign
- Redis handles increased event throughput
- Independent pod scaling

### Fault Tolerance
- No single point of failure
- Component isolation prevents cascade failures
- Event replay for recovery scenarios

## Performance Considerations

### Latency
- Event-driven architecture minimizes delays
- Gemini 3 response optimization
- Local caching for frequent decisions

### Throughput
- Redis pub/sub for high-volume events
- Asynchronous pod decision processing
- Batch processing for non-critical operations

## Security & Reliability

### Event Validation
- Type-safe event definitions
- Input validation for all external data
- Audit logging for system events

### Error Handling
- Graceful degradation for Gemini 3 failures
- Circuit breakers for external dependencies
- Automatic retry with exponential backoff



                       ┌──────────────┐
                       │  AexisSystem │ (Single Instance)
                       └──────┬───────┘
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
       ┌──────────┐    ┌──────────┐    ┌──────────┐
       │   CLI    │    │   API    │    │Dashboard │
       │(console) │    │ (routes) │    │  (web)   │
       └──────────┘    └────┬─────┘    └────┬─────┘
                            │               │
                            │  Redis PubSub │
                            └───────┬───────┘
                                    ▼
                             ┌──────────────┐
                             │  Visualizer  │  (WebSocket)
                             │     (TS)     │
                             └──────────────┘
