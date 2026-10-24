from __future__ import annotations

from enum import Enum


class Good(str, Enum):
    FOOD = "food"
    COAL = "coal"
    IRON_ORE = "iron_ore"
    STEEL = "steel"
    BRICK = "brick"
    CLOTH = "cloth"
    FERTILIZER = "fertilizer"
    MACHINERY = "machinery"
    BUILDING = "building"


class Industry(str, Enum):
    AGRICULTURE = "agriculture"
    COAL_MINE = "coal_mine"
    IRON_MINE = "iron_mine"
    STEEL_MILL = "steel_mill"
    BRICK_FACTORY = "brick_factory"
    TEXTILE_MILL = "textile_mill"
    MACHINERY_FACTORY = "machinery_factory"
    CONSTRUCTION = "construction"
    FERTILIZER_FACTORY = "fertilizer_factory"


CONSUMER_GOODS = frozenset({Good.FOOD, Good.CLOTH, Good.BUILDING})
CAPITAL_GOODS = frozenset({Good.MACHINERY, Good.BRICK, Good.STEEL})
