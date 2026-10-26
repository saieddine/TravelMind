
from agents.destination_agent import DestinationAgent


def test_nature_interest_selects_nature_attractions():
    agent = DestinationAgent()

    results = agent.run("Chengdu", ["nature"])

    assert results
    assert all(
        "nature" in [
            interest.casefold()
            for interest in place["interests"]
        ]
        for place in results
    )


def test_unsupported_destination_returns_no_attractions():
    agent = DestinationAgent()

    results = agent.run("Beijing", ["culture"])

    assert results == []


def test_empty_interests_returns_available_attractions():
    agent = DestinationAgent()

    results = agent.run("Chengdu", [])

    assert results
