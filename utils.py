# --- App Configuration ---
from dataclasses import dataclass, field
from enum import Enum

class PreRating(Enum):
    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"

@dataclass
class Player:
    name: str
    gender: str
    pre_rating: PreRating
    rating: int = field(init=False)
    earned_rating: int = 0

    def __post_init__(self):
        self.rating = self.get_initial_rating()

    def get_initial_rating(self):
        if self.pre_rating == PreRating.ADVANCED:
            return 3
        elif self.pre_rating == PreRating.INTERMEDIATE:
            return 2
        elif self.pre_rating == PreRating.BEGINNER:
            return 1
        return 0

    def add_rating(self, amount: int):
        """Adds rating to the player."""
        self.rating += amount
        self.earned_rating += amount
