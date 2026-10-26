from data.attractions import ATTRACTIONS


class DestinationAgent:
    """Select attractions using a traveler's stated interests."""

    def run(self, destination: str, interests: list[str]) -> list[dict]:
        if destination.strip().casefold() != "chengdu":
            return []

        requested = {
            interest.strip().casefold()
            for interest in interests
            if interest.strip()
        }

        ranked = sorted(
            ATTRACTIONS,
            key=lambda place: sum(
                interest.casefold() in requested
                for interest in place["interests"]
            ),
            reverse=True,
        )

        if not requested:
            return ranked

        matches = [
            place for place in ranked
            if any(
                interest.casefold() in requested
                for interest in place["interests"]
            )
        ]

        return matches if matches else ranked
