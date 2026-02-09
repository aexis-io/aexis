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
./run_services.sh
```

Access the dashboard at http://localhost:8000

To simulate passenger and cargo arrival
run the injector script
```bash
python payload_injectory.py
```
