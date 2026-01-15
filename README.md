# AEXIS - Autonomous Event-Driven Transportation Intelligence System

A decentralized autonomous transportation system powered by Gemini 3 AI, built for the Gemini 3 Hackathon.

## Overview

AEXIS models interlinked transit stations where autonomous Pods (agents) service dynamic inflows of passengers and cargo without central control. The system uses Gemini 3 as the "brain" for pod decisions, leveraging Thought Signatures for continuity and multi-step reasoning for intelligent route optimization.

## Architecture

### Event-Driven Design
- **Message Bus**: Redis pub/sub for real-time event distribution
- **Decentralized Control**: Each pod makes independent decisions using Gemini 3
- **Event Types**: Passenger arrivals, cargo requests, pod availability, congestion alerts

### Core Components
- **Stations**: Network nodes handling passenger/cargo inflows
- **Pods**: Autonomous vehicles with Gemini 3 decision-making
- **Message Bus**: Redis-based event coordination
- **Web Dashboard**: FastAPI real-time monitoring interface

### Gemini 3 Integration
- **Thought Signatures**: Maintain pod decision continuity across events
- **Multi-Level Reasoning**: Route optimization, capacity assessment, congestion prediction
- **Real-Time Decisions**: Sub-second response to transportation events

## Features

- 🚀 **Event-Driven Architecture**: Reactive, scalable system design
- 🧠 **AI-Powered Decisions**: Gemini 3 for intelligent pod routing
- 📊 **Real-Time Dashboard**: Live monitoring of system performance
- 🔄 **Fault Tolerant**: Snapshotting and recovery mechanisms
- 🌐 **Mixed Transit**: Handles both passengers and cargo dynamically

## Quick Start

### Prerequisites
- Python 3.12+
- Docker & Docker Compose
- Gemini 3 API key

### Setup

1. **Clone and Setup**
```bash
git clone <repository>
cd aexis
cp .env.example .env
# Edit .env with your API keys
```

2. **Start Redis**
```bash
docker compose up -d
```

3. **Install Dependencies**
```bash
cd aexis
uv sync
```

4. **Run the System**
```bash
uv run python main.py
```

5. **Access Dashboard**
Open http://localhost:8000 in your browser

## Configuration

### Environment Variables
- `REDIS_PASSWORD`: Redis authentication password
- `GEMINI_API_KEY`: Your Gemini 3 API key
- `POD_COUNT`: Number of autonomous pods (default: 25)
- `STATION_COUNT`: Number of transit stations (default: 8)
- `UI_PORT`: Web dashboard port (default: 8000)

### System Parameters
- **Station Network**: Configurable topology and locations
- **Inflow Rates**: Dynamic passenger/cargo arrival patterns
- **Pod Capacity**: Weight and passenger limits per vehicle
- **Decision Latency**: Gemini 3 response timeout settings

## Project Structure

```
aexis/
├── aexis/
│   ├── core/
│   │   ├── __init__.py          # Gemini model configuration
│   │   ├── message_bus.py       # Redis event system
│   │   ├── events.py           # Event type definitions
│   │   ├── pod.py              # Autonomous pod logic
│   │   ├── station.py          # Station management
│   │   └── system.py           # Main system coordinator
│   ├── ui/
│   │   ├── app.py              # FastAPI dashboard
│   │   ├── static/             # CSS/JS assets
│   │   └── templates/          # HTML templates
│   └── main.py                 # System entry point
├── docker-compose.yml          # Redis configuration
├── pyproject.toml             # Python dependencies
└── README.md                  # This file
```

## Hackathon Demo

### Scenario
Mixed urban transit system with 25 autonomous pods serving 8 stations, handling both passenger requests and cargo deliveries in real-time.

### Key Demonstrations
1. **Decentralized Decision-Making**: Each pod independently chooses routes using Gemini 3
2. **Emergent Behavior**: System self-organizes to handle congestion and demand spikes
3. **AI Continuity**: Thought Signatures maintain consistent pod behavior across events
4. **Real-Time Monitoring**: Live dashboard showing system performance and AI decisions

### Success Metrics
- **Throughput**: Passengers/cargo delivered per minute
- **Efficiency**: Average delivery time vs. optimal
- **Adaptability**: Response to sudden demand changes
- **Reliability**: System uptime and fault recovery

## Technology Stack

- **Backend**: Python 3.12, FastAPI, Redis
- **AI**: Google Gemini 3 API with Thought Signatures
- **Frontend**: HTML5, JavaScript, WebSocket
- **Infrastructure**: Docker, NetworkX for graph operations

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Gemini 3 Hackathon

Built for the [Gemini 3 Hackathon](https://gemini3.devpost.com/) - demonstrating next-generation AI applications with advanced reasoning capabilities.

### Gemini 3 Features Used
- **Thought Signatures**: Persistent AI reasoning across events
- **Multi-Level Thinking**: Complex decision hierarchies
- **Low Latency**: Real-time response for transportation logistics
- **Advanced Reasoning**: Route optimization and system coordination
