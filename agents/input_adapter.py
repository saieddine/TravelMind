from pydantic import ValidationError

from models.attraction import AttractionInput


def convert_destination_places(
    places: list[dict],
) -> list[AttractionInput]:
    """
    Convert Destination Agent recommendations into
    the input format required by the Itinerary Agent.
    """

    # Validate every attraction against the agreed input model
    attractions = []

    for index, place in enumerate(places):
        try:
            attraction = AttractionInput.model_validate(place)
            attractions.append(attraction)

        except ValidationError as error:
            raise ValueError(
                f"Invalid attraction data at places[{index}]: {error}"
            ) from error

    return attractions