# Setup Guide

## Prerequisites

- Python 3.12+
- Docker & Docker Compose
- Gemini 3 API key
- Redis (handled by Docker Compose)

## Installation

### 1. Clone Repository
```bash
git clone <repository-url>
cd aexis
```

### 2. Environment Configuration
```bash
cp .env.example .env
# Edit .env with your actual API keys and preferences
```

### 3. Start Redis
```bash
docker compose up -d
```

### 4. Install Python Dependencies
```bash
cd aexis
uv sync
```

### 5. Verify Setup
```bash
# Test Redis connection
uv run python -c "import redis; r=redis.Redis(); print('Redis OK' if r.ping() else 'Redis Failed')"

# Test Gemini API (requires API key)
uv run python -c "from google import genai; client=genai.Client(); print('Gemini OK')"
```

## Configuration

### Environment Variables

Create `.env` file with:

```bash
# Redis Configuration
REDIS_PASSWORD=your_secure_password
REDIS_HOST=localhost
REDIS_PORT=6379

# Gemini API Configuration
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3-pro-preview

# System Configuration
POD_COUNT=25
STATION_COUNT=8
UI_PORT=8000
```

### System Parameters

#### Station Network
- **Topology**: Configurable graph structure
- **Locations**: Geographic coordinates or logical positions
- **Capacity**: Passenger/cargo handling limits

#### Pod Fleet
- **Count**: Number of autonomous vehicles
- **Capacity**: Weight and passenger limits per pod
- **Speed**: Movement rate between stations

#### Inflow Patterns
- **Passenger Rate**: Arrival frequency per station
- **Cargo Rate**: Delivery request frequency
- **Peak Hours**: Time-based demand variations

## Running the System

### Development Mode
```bash
cd aexis
uv run python main.py
```

### Production Mode
```bash
# With proper environment variables
export REDIS_PASSWORD=your_password
export GEMINI_API_KEY=your_key
uv run python main.py
```

## Access Points

- **Web Dashboard**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **WebSocket Events**: ws://localhost:8000/ws

## Troubleshooting

### Common Issues

#### Redis Connection Failed
```bash
# Check Redis container
docker compose ps
docker compose logs aexis-redis

# Restart if needed
docker compose restart aexis-redis
```

#### Gemini API Errors
- Verify API key in `.env`
- Check Gemini 3 API access
- Confirm model name: `gemini-3-pro-preview`

#### Dependency Issues
```bash
# Clear and reinstall
rm -rf .venv
uv sync
```

### Debug Mode
```bash
# Enable debug logging
export AEXIS_DEBUG=1
uv run python main.py
```

## Development Workflow

### Adding New Event Types
1. Define event in `aexis/core/events.py`
2. Add handler in relevant component
3. Update Redis channel subscriptions
4. Add UI visualization if needed

### Modifying Pod Behavior
1. Update decision prompts in `aexis/core/pod.py`
2. Adjust Thought Signature usage
3. Test with various scenarios
4. Monitor Gemini 3 API usage

### Extending Dashboard
1. Add new endpoints in `aexis/ui/app.py`
2. Create HTML templates in `aexis/ui/templates/`
3. Add JavaScript for real-time updates
4. Style with CSS in `aexis/ui/static/`
