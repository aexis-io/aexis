# AEXIS - Autonomous Event-Driven Transportation Intelligence System

A decentralized autonomous transportation system powered by Gemini 3 AI, built for the Gemini 3 Hackathon.

## Overview

AEXIS models interlinked transit stations where autonomous Pods (agents) service dynamic inflows of passengers and cargo without central control. The system uses Gemini 3 as the "brain" for pod decisions, leveraging Thought Signatures for continuity and multi-step reasoning for intelligent route optimization.

## Key Features

- 🚀 **Event-Driven Architecture**: Reactive, scalable system design
- 🧠 **AI-Powered Decisions**: Gemini 3 for intelligent pod routing
- 📊 **Real-Time Dashboard**: Live monitoring of system performance
- 🔄 **Fault Tolerant**: Snapshotting and recovery mechanisms
- 🌐 **Mixed Transit**: Handles both passengers and cargo dynamically

## Quick Start

```bash
# Clone and setup
git clone <repository>
cd aexis
cp .env.example .env

# Start Redis
docker compose up -d

# Install dependencies and run
cd aexis
uv sync
uv run python main.py
```

Access the dashboard at http://localhost:8000

## Documentation

- **[Architecture](docs/architecture.md)** - System design and component overview
- **[Setup Guide](docs/setup.md)** - Installation and configuration instructions  
- **[API Reference](docs/api.md)** - Complete API documentation and event types
- **[Graph Visualization](docs/graph-visualization.md)** - Real-time network visualization design

## Gemini 3 Hackathon

Built for the [Gemini 3 Hackathon](https://gemini3.devpost.com/) - demonstrating next-generation AI applications with advanced reasoning capabilities.

### Gemini 3 Features Used
- **Thought Signatures**: Persistent AI reasoning across events
- **Multi-Level Thinking**: Complex decision hierarchies
- **Low Latency**: Real-time response for transportation logistics
- **Advanced Reasoning**: Route optimization and system coordination
