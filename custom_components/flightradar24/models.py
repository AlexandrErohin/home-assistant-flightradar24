from dataclasses import dataclass


@dataclass(slots=True)
class BoundingBox:
    """Bounding box for retrieving state vectors."""

    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float

    def validate(self) -> None:
        """Validate if the latitude and longitude are correct."""
        self._check_latitude(self.min_latitude)
        self._check_latitude(self.max_latitude)
        self._check_longitude(self.min_longitude)
        self._check_longitude(self.max_longitude)

    def get_string(self) -> str:
        return "{},{},{},{}".format(self.max_latitude, self.min_latitude, self.min_longitude, self.max_longitude)

    @staticmethod
    def _check_latitude(degrees: float) -> None:
        if degrees < -90 or degrees > 90:
            msg = f"Invalid latitude {degrees}! Must be in [-90, 90]."
            raise Exception(msg)

    @staticmethod
    def _check_longitude(degrees: float) -> None:
        if degrees < -180 or degrees > 180:
            msg = f"Invalid longitude {degrees}! Must be in [-180, 180]."
            raise Exception(msg)
