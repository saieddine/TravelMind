# Sasha: Destination, Context and provider integration

This contribution extends the root packages already present on main. It does not add another travelmind/src agent architecture. The original local TravelMind project is unchanged. No branch was merged, no files were staged, and no commits or pushes were made.

## Current architecture and preserved interfaces

`models.TripRequest` is authoritative and reused unchanged. No EvidenceRecord exists on current main or the inspected backend branch. `main.py`, `models.py`, `itinerary.py`, the shared Chengdu dataset and the existing Destination tests are unchanged. The README's original backend/frontend instructions are retained; the checked-out backend contains requirements only and no app package/frontend.

`agents.destination_agent.DestinationAgent.run(destination, interests)` retains the original Chengdu list interface used by the existing Coordinator and planner. The same class now exposes `run_candidates(text, ...)` for Sasha's richer dictionary results. There is no competing Destination class. `agents.context_agent.ContextAgent.run(...)` provides weather context. Existing `plan_trip` behavior and API routes are unchanged.

`TravelMindOrchestrator.collect_agent_results(trip, ...)` is an additive offline collection entry point, using the actual TripRequest and the existing Destination instance. It returns the request, candidate result, context result, traces and zero-call collection usage. No itinerary is synthesized by this method. Routing is explicitly not requested; call the routing adapter separately with permission. A supplied LLM city conflicting with TripRequest is rejected. Upstream LLM usage belongs to the caller, not this zero-call collection.

## Setup and safe checks

Run from the shared repository root with Python 3.12:

```powershell
python -m pip install -r requirements.txt
python -B -m scripts.test_offline
python -m scripts.demo --text "History and museums in Xi'an" --scenario rain
python -m scripts.llm --mode smoke
```

The test runner executes all existing root test functions and the full imported unittest suite, with outbound sockets blocked. pytest is not required for the current plain root functions. If future team tests use pytest fixtures, extend the runner or use the team's pytest environment. Existing backend dependencies are retained; requirements-sasha.txt adds requests, python-dotenv and explicit Pydantic v2. No packages/services were downloaded during integration. FastAPI/uvicorn are not installed in the validation interpreter, so HTTP startup is not claimed tested.

The five existing itinerary tests incorrectly called generate_itinerary with one argument; their existing generate_for_test helper already supplied both required inputs. Only those call sites were updated. Assertions and production itinerary code were preserved.

## Coordinator usage

```python
from models import TripRequest
from orchestrator import TravelMindOrchestrator

trip = TripRequest(origin="Beijing", destination="Xi'an", days=2,
                   budget=3000, travelers=2, interests=["museum"])
result = TravelMindOrchestrator().collect_agent_results(trip, scenario="rain")
places = result["destination"]["places"]
```

For direct use:

```python
from agents.destination_agent import DestinationAgent
from agents.context_agent import ContextAgent

candidates = DestinationAgent().run_candidates("Museums in Xi'an")
context = ContextAgent().run(city=candidates["request"]["city"], scenario="rain")
```

The richer offline seed covers Xi'an; it does not duplicate the existing Chengdu illustrative dataset. Therefore a richer Chengdu query can return no local matches, while the original Chengdu planner remains functional. Neither path silently switches to a live service. Explicit parsed LLM intent reaches run_candidates via interpreted_intent and bypasses rules; null city requires clarification. Tests prove the actual parsed city/interests/category reach retrieval.

## Intent validation and clarification

`llm.intent_interpreter.validate_intent` is shared by the Coordinator boundary, parsed-intent Destination boundary, direct AI mode and strict JSON parser. It checks object shape, all required fields/types, whitelists and known parser metadata before using or normalizing intent fields. Missing keys, numeric/empty cities, invalid interests/category and unexpected structures raise `IntentValidationError` (`code="invalid_intent"`), a ValueError subtype. Invalid inputs are not defaulted and cannot reach retrieval.

A structurally valid `city: null` is different: without a resolved destination, Destination raises `ClarificationRequired` (`code="clarification_required"`, `field="city"`, `places=[]`). It is also ValueError-compatible. Catch it first to ask the traveler for a destination; catch IntentValidationError separately to reject malformed input. Neither raw KeyError nor AttributeError is exposed for malformed intent.

Direct `ai=True` may resolve a null AI city from a valid explicit city argument or a recognized city in the user's text. It cannot use the demonstration Xi'an default as a resolved city. Supplied `interpreted_intent` remains authoritative and does not reparse text; a valid explicit city argument can resolve its null city. The Coordinator's actual TripRequest destination is such an explicit input, so a null model city can safely resolve from that request. A conflicting non-null model city is still rejected. Non-AI demonstration defaults and the original Chengdu run interface are unchanged.

Clarification exceptions carry a usage/trace snapshot. Direct AI mode preserves measured usage; Stage 17 adds its already-measured OpenRouter usage and trace before propagating clarification. No attraction retrieval occurs, even if live=True was supplied. The Coordinator propagates the ValueError-compatible exception; no competing authoritative error model is invented.

```python
from llm.intent_interpreter import ClarificationRequired, IntentValidationError

try:
    result = agent.run_candidates(text, interpreted_intent=validated_plan)
except ClarificationRequired as exc:
    # Ask for exc.field; exc.places is empty. Account for exc.usage/trace.
    pass
except IntentValidationError:
    # Reject malformed intent; do not select a default destination.
    pass
```

Regression tests include real Xi'an seed retrieval, mocked Chengdu retrieval routing, and real legacy Chengdu behavior. They do not invent new Chengdu seed records or make live calls.

## Itinerary contract adapters

`integration.itinerary_adapter.to_itinerary_places(places, attraction_model=...)` adds the id alias while retaining attraction_id, names, location, provenance, selection reason, per-person costs and unknowns. It normalizes status labels to verified/estimated/unknown without promoting unknown information (numeric fields marked unknown remain null), and preserves coordinate-system labels. Pass Nirmin's actual model class to validate; it is not copied or redefined here. Missing English names are not fabricated and can fail his current non-nullable name_en field.

The inspected remote-tracking branch origin/nirmin/itinerary-critic-backend has `run_itinerary_task(request, destination_result, budget_assumptions=None)` and `AttractionInput`. His agent accepts a dictionary containing places. After teammate integration supplies the real imports:

```python
from integration.itinerary_adapter import to_itinerary_places

places = to_itinerary_places(result["destination"]["places"],
                            attraction_model=AttractionInput)  # actual teammate class
itinerary_result = run_itinerary_task(trip, {"places": places})
```

AttractionInput and run_itinerary_task are intentionally not imported above: they exist only on the unmerged branch, whose bare agents/models imports collide with this repository's root packages. Agree on package names with Nirmin before merging. The actual reference AttractionInput model was inspected and tested against our candidate output offline; the complete remote pipeline was not integrated or claimed working. Unknown durations remain unassigned by his scheduler, not guessed.

The main-branch legacy planner requires duration_hours and numeric entry_cost. `to_legacy_itinerary_places` converts known per-person values and rejects null/unknown values. It never supplies a free price or guessed duration. The current API still calls the original Chengdu pipeline; it is not automatically wired to Xi'an candidate results.

## Provider modules, resources and permissions

- providers/amap: distinct POI v3/v5 and weather adapters.
- providers/routing: Amap Route Planning 2.0.
- providers/baidu: explicitly allowed named-place alternative, not cross-provider record blending.
- providers/weather: Open-Meteo and its weather-context bridge.
- providers/wikimedia: background content with a contact user-agent.
- providers/official_sources: reviewed registry, robots-aware fetch, conservative claim extraction.
- providers/inventory: guarded Duffel test sandbox and provider gateway; Qunar approval-pending and live hotels unavailable.
- data: authored seed search, enrichment, provider routing and POI filtering; data/sasha contains three authored JSON files and three synthetic HTML fixtures.
- integration: candidate/team handoffs, actual-model contract audit and the two shared adapters.
- workflows: reusable enrichment, official verification and route handoff functions required by tests. Historical numbered scripts, archives, logs, caches and private environments were not copied.

Amap uses GCJ-02, Open-Meteo uses WGS84; labels remain distinct. Unknown costs stay null and estimated_cost_cny is per person. Average spend is not admission cost; published opening hours do not guarantee future access. Outputs are candidates, not scheduled itineraries. Provider failures must be handled by the Coordinator's eventual authoritative error contract; unavailable information is never invented. Do not persist Amap/Baidu results without provider permission.

## Optional environment/live use (not run during integration)

Copy .env.example only if no .env exists. Config reads only the shared-root private .env; no credentials were copied from the local project. Existing process environment overrides .env; --model overrides OPENROUTER_MODEL. Set OPENROUTER_MODEL=openrouter/free for the official free router. Only exact openrouter/free and IDs ending in :free are allowed; paid models remain blocked even with the legacy flag. No automatic retries or paid fallback. Diagnostics record requested and actual returned model, output/reasoning tokens, final-text presence, and sanitized HTTP 429 metadata/headers.

`python -m scripts.llm --mode smoke --live-llm` explicitly authorizes one LLM request. `--mode destination --live-llm --text "Museums in Xi'an"` authorizes one strict-intent request followed by local candidate retrieval, with actual usage/traces. `python -m agents.destination_agent --text "Museums in Xi'an" --live` separately authorizes place-provider access. Do not use live flags in automated tests. Gemma/Nemotron reasoning controls are scoped to those exact model IDs and are not applied to openrouter/free.

Optional variables: OPENROUTER_API_KEY, AMAP_API_KEY, BAIDU_MAP_AK, DUFFEL_TEST_TOKEN, TRAVELMIND_WIKIMEDIA_CONTACT. Free provider quotas can fail independently of your OpenRouter account quota. There are no live verification claims from this integration.

## Remaining team decisions

Authoritative EvidenceRecord/AgentResult types, Context Agent backend envelope, API route wiring for the richer path, Nirmin package import isolation, required/null English names, travel dates absent from TripRequest, approved live inventory access and provider retention permissions remain open. No teammate schemas were invented or silently changed. See SASHA_VALIDATION.json and SASHA_CHANGE_MANIFEST.json for actual checks and files.
