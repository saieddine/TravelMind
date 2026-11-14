# TravelMind — Itinerary Planning & Critic Module

## 1. Overview

This module is responsible for generating, scheduling, and evaluating travel itineraries in the TravelMind project.

It takes attraction recommendations and user travel requirements as input, organizes selected attractions into a daily schedule, checks budget and time constraints, and evaluates the quality of the generated itinerary.

The module also integrates an LLM through OpenRouter to improve attraction prioritization and provide additional qualitative feedback.

## 2. Main Responsibilities

### Itinerary Agent

File: `agents/itinerary_agent.py`

- Receives attraction recommendations from the Destination Agent.
- Prioritizes attractions based on available information and user preferences.
- Schedules attractions across the requested number of days.
- Respects daily activity time limits.
- Tracks estimated activity and admission costs.
- Identifies attractions that cannot be scheduled and records the reasons.

### Critic Agent

File: `agents/critic_agent.py`

- Evaluates the generated itinerary.
- Checks scheduling and budget-related constraints.
- Identifies potential issues in daily pacing, activity variety, and itinerary coherence.
- Provides suggestions for improving the itinerary.
- Combines deterministic validation with optional AI-generated qualitative feedback.

### Itinerary Pipeline

File: `agents/itinerary_pipeline.py`

- Coordinates itinerary generation and evaluation.
- Passes user preferences to the Itinerary Agent.
- Runs the Critic Agent.
- Manages the revision and evaluation workflow.

### Team Interface

File: `agents/team_interface.py`

- Connects the itinerary module to the wider TravelMind system.
- Receives the trip request and Destination Agent results.
- Extracts relevant travel information and optional user preferences.
- Returns results through the shared team interface.

### LLM Client

File: `agents/llm_client.py`

- Handles communication with OpenRouter.
- Uses an OpenAI-compatible API client.
- Provides access to the configured language model.
- Handles API errors and unavailable responses gracefully.

## 3. AI Integration

The module uses OpenRouter to access an LLM.

**Current configured model:**

`nvidia/nemotron-3.5-lightning:free`

The LLM is used for two main tasks:

1. Attraction prioritization: suggests a better order for attractions based on their available information and user preferences.
2. Qualitative itinerary review: evaluates activity variety, daily pacing, repetition, and overall coherence.

The LLM supplements the existing Python logic. It does not replace deterministic scheduling, budget calculations, or validation.

If the API is disabled, unavailable, or returns invalid data, the module falls back to its existing Python logic.

## 4. Configuration

Create a `.env` file in the project root:

```env
OPENROUTER_API_KEY=your_api_key
ENABLE_OPENROUTER=true
OPENROUTER_MODEL=nvidia/nemotron-3.5-lightning:free
```

Never commit the `.env` file or expose your API key.

Set `ENABLE_OPENROUTER=false` to disable LLM requests and use the deterministic implementation.

## 5. Installation

Install the project dependencies:

```bash
pip install -r requirements.txt
```

The LLM integration uses:

- `openai`
- `python-dotenv`

## 6. Testing

Run the project tests from the project root:

```bash
python -m pytest -q
```

To run tests without making OpenRouter API requests:

```powershell
$env:ENABLE_OPENROUTER="false"
py -m pytest -q
```

The existing test suite passed **60 tests** during development.

## 7. Important Implementation Details

- Attraction costs represent per-person admission or activity costs.
- Transportation, accommodation, and meals are not included in attraction costs.
- A cost of `0` represents a verified free activity.
- A `null` cost represents unknown cost information.
- Group attraction costs are calculated using the per-person cost multiplied by the number of travelers.
- The overall trip budget also accounts for accommodation, meals, and local transportation.
- The default daily activity time limit is 360 minutes and can be configured.
- Attractions that cannot be scheduled are recorded rather than silently discarded.

## 8. Contribution Summary

My contribution to TravelMind focuses on the itinerary planning and evaluation layer.

It transforms attraction recommendations into structured daily itineraries, applies scheduling and budget constraints, evaluates itinerary quality, and integrates an optional LLM to improve prioritization and qualitative feedback.

The implementation is designed to work both with and without external LLM access.
