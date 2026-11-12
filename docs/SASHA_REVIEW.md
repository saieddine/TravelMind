# Sasha integration review

Prepared on feature/sasha-destination-context from main at 88fbd90e46173a50b37bed0191f0b6474eefe696. All changes are local and unstaged. No commits, pushes, merges or history rewrites. The original cleaned TravelMind directory is unchanged. Local Git references were inspected without fetching or contacting GitHub.

## Architecture and integration plan executed

Extend existing root agents/data packages; add provider, llm, integration and workflow packages. Do not copy the local project's competing src/travelmind package or its packaging setup. Keep the existing Chengdu Destination interface and current HTTP planner; expose richer candidate collection additively. Use the real models.TripRequest. No EvidenceRecord was found and none was invented. See SASHA_MIGRATION.json for all source-to-shared module mappings.

The same DestinationAgent class has its original run(destination, interests) list API and new run_candidates(text, ...) dictionary API. Coordinator.collect_agent_results uses the richer path with Context and serializes the real TripRequest. LLM intent bypasses rule parsing; conflicting explicit TripRequest destinations are rejected. The imported provider workflows and adapters preserve original provenance, coordinate systems, opt-in calls and token accounting.

Unknown costs/durations remain null. The Itinerary adapter preserves attraction_id, adds id, normalizes enum labels and validates supplied actual teammate classes. Names, selection reason and source/provenance are retained. The main planner adapter rejects incomplete numeric data rather than guessing/free pricing.

## Final validation gaps resolved

A shared intent validator now rejects malformed structures/types before boundary field access or normalization. IntentValidationError(code="invalid_intent") distinguishes malformed input from a valid unresolved city. ClarificationRequired(code="clarification_required", field="city", places=[]) stops retrieval when neither AI intent nor an explicit/recognized user destination resolves the city. Both extend ValueError, preserving caller compatibility. No raw KeyError/AttributeError or silent AI-to-Xi'an default remains in the reviewed cases. Stage 17 propagates clarification with measured usage/traces intact. Non-AI demo defaults and legacy Chengdu behavior are preserved.

Actual mocked missing-city demonstration: code=clarification_required; places=[]; local retrieval calls=0; Amap retrieval calls=0. Real API/LLM calls during verification remain zero. Correctly structured Coordinator intent reaches real offline Xi'an retrieval; authoritative TripRequest can resolve a null model city. Chengdu AI query routing is tested with a synthetic search fixture; the richer seed is still Xi'an-focused.

Production files changed for these fixes: agents/destination_agent.py, integration/coordinator_adapter.py, llm/intent_interpreter.py and scripts/llm.py. Added tests_sasha/test_intent_validation.py. Documentation/validation/manifest/tree reports were refreshed; no authoritative models or itinerary implementation changed. See SASHA_VALIDATION.json for machine-readable demonstrations and complete test results.

## Actual reference contracts

TripRequest is imported from the unchanged root models.py. Nirmin's unmerged remote-tracking branch at d6f3875b4f1eec40b62dff2a1e9022006451503a contains AttractionInput and run_itinerary_task(request, destination_result, budget_assumptions=None). The actual model was read from the local Git object and validated against 2 candidates; no model source was copied into the contribution. Missing name_en is rejected according to that actual model.

Nirmin's agents/models bare imports collide with this repository's root agents package/models.py; his branch was not merged. Supplying his actual model class and pipeline after namespace alignment is still a team task. No working end-to-end Nirmin/HTTP pipeline is claimed.

## Functional checks

- 217 passed; 0 failed; 0 test/import errors; 0 skipped.
- All original 201 tests plus 16 new intent-validation regression methods executed (217 total).
- 46 application modules imported with outbound sockets blocked.
- Combined offline demo and offline LLM smoke mode passed with zero request/token usage.
- Existing main-branch planner behavior checked for Chengdu success and unsupported destinations.
- Model identity, token accounting, strict JSON intent, HTTP 429 diagnostics, provenance and missing-data tests retained.
- Existing baseline team suite had 5 TypeErrors: tests omitted selected_attractions. Those five calls now use their already-existing helper. No assertions weakened and no production itinerary changes.
- FastAPI/uvicorn are not installed in this interpreter; HTTP application startup was not tested. Existing team dependency declarations are preserved and include the required backend dependencies.

Run from the shared root: `python -B -m scripts.test_offline`. This executes current root plain test functions without requiring pytest, plus the full imported unittest suite, with sockets blocked. Future fixture-dependent pytest tests need the team's pytest runner.

## Security and Git review

- Current branch verified: feature/sasha-destination-context; main still points to the original base commit.
- Nothing staged; no merge conflicts and no tracked-file deletions.
- git diff --check passes; newly added text files have no trailing-whitespace/conflict-marker findings.
- No credential-shaped literal findings; no added files exceed 1 MB. Pattern scanning cannot prove the absence of every possible secret format.
- .env/.venv and bytecode are ignored; safe .env.example remains shareable. No private key/environment, archive, virtual environment, Git directory, cache or generated local development file was copied.
- Only three authored JSON resources and three synthetic HTML fixtures were imported, not captured live Amap/Baidu responses.
- External API calls: 0. LLM calls/tokens: 0. No packages or paid services installed.
- Protected unchanged: models.py, itinerary.py, main.py, data/attractions.py, existing package markers and test_destination_agent.py.

## Remaining integration work

1. Decide how/when Saieddine's HTTP/Coordinator workflow should opt into richer collection; existing API routes stay unchanged.
2. Integrate Nirmin's package under nonconflicting imports and agree on missing English-name handling.
3. Supply actual EvidenceRecord/AgentResult/error-envelope contracts and travel-date fields; none were invented.
4. Add known/approved duration and per-person cost evidence if scheduling is required. Unknown durations are intentionally unschedulable.
5. Richer seed data is Xi'an-focused; the original shared Chengdu dataset remains on its legacy path, not silently duplicated or relabeled as verified data.
6. Provider access, live inventory (Qunar/hotels) and retention approvals remain external dependencies. No live provider verification was performed.
7. Install existing backend requirements in the team's chosen environment before HTTP startup testing.

## Changed files

7 modified tracked files; 81 added/untracked files. The exact machine-readable list is SASHA_CHANGE_MANIFEST.json and full shareable tree is SASHA_DIRECTORY_TREE.txt.

Modified:

- `.gitignore`
- `README.md`
- `agents/destination_agent.py`
- `backend/requirements.txt`
- `orchestrator.py`
- `requirements.txt`
- `test_itinerary.py`

Added/untracked:

- `.env.example`
- `agents/context_agent.py`
- `data/dataset.py`
- `data/enrichment.py`
- `data/poi_quality.py`
- `data/provider_router.py`
- `data/sasha/attractions_seed.json`
- `data/sasha/fixtures/bmy_guide_demo.html`
- `data/sasha/fixtures/bmy_tickets_demo.html`
- `data/sasha/fixtures/sxhm_2026_demo.html`
- `data/sasha/official_attractions_curated.json`
- `data/sasha/official_source_registry.json`
- `docs/SASHA_CHANGE_MANIFEST.json`
- `docs/SASHA_DIRECTORY_TREE.txt`
- `docs/SASHA_INTEGRATION.md`
- `docs/SASHA_MIGRATION.json`
- `docs/SASHA_REVIEW.md`
- `docs/SASHA_TEST_RESULTS.txt`
- `docs/SASHA_VALIDATION.json`
- `integration/__init__.py`
- `integration/candidate_handoff.py`
- `integration/contract_validation.py`
- `integration/coordinator_adapter.py`
- `integration/itinerary_adapter.py`
- `integration/team_handoff.py`
- `llm/__init__.py`
- `llm/intent_interpreter.py`
- `llm/openrouter_client.py`
- `providers/__init__.py`
- `providers/amap/__init__.py`
- `providers/amap/client.py`
- `providers/amap/poi_v5.py`
- `providers/amap/weather.py`
- `providers/baidu/__init__.py`
- `providers/baidu/places.py`
- `providers/config.py`
- `providers/inventory/__init__.py`
- `providers/inventory/gateway.py`
- `providers/inventory/sandbox.py`
- `providers/official_sources/__init__.py`
- `providers/official_sources/client.py`
- `providers/official_sources/extract.py`
- `providers/routing/__init__.py`
- `providers/routing/amap.py`
- `providers/weather/__init__.py`
- `providers/weather/context.py`
- `providers/weather/open_meteo.py`
- `providers/wikimedia/__init__.py`
- `providers/wikimedia/content.py`
- `requirements-sasha.txt`
- `scripts/__init__.py`
- `scripts/demo.py`
- `scripts/llm.py`
- `scripts/test_offline.py`
- `tests_sasha/__init__.py`
- `tests_sasha/test_amap_weather.py`
- `tests_sasha/test_attraction_enrichment.py`
- `tests_sasha/test_context_agent.py`
- `tests_sasha/test_destination_agent.py`
- `tests_sasha/test_destination_dataset.py`
- `tests_sasha/test_intent_validation.py`
- `tests_sasha/test_open_meteo.py`
- `tests_sasha/test_openrouter_diagnostics.py`
- `tests_sasha/test_package_integration.py`
- `tests_sasha/test_shared_integration.py`
- `tests_sasha/test_stage11.py`
- `tests_sasha/test_stage12.py`
- `tests_sasha/test_stage13.py`
- `tests_sasha/test_stage14.py`
- `tests_sasha/test_stage15.py`
- `tests_sasha/test_stage16.py`
- `tests_sasha/test_stage17.py`
- `tests_sasha/test_stage6.py`
- `tests_sasha/test_stage7.py`
- `tests_sasha/test_stage8.py`
- `tests_sasha/test_stage9.py`
- `tests_sasha/test_weather_probability_stage11.py`
- `workflows/__init__.py`
- `workflows/enrichment.py`
- `workflows/official_verification.py`
- `workflows/routes.py`
