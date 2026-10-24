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
    SERVICE = "service"


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
    SERVICE = "service"


CONSUMER_GOODS = frozenset(
    {Good.FOOD, Good.CLOTH, Good.BUILDING, Good.SERVICE}
)
CAPITAL_GOODS = frozenset({Good.MACHINERY, Good.BRICK, Good.STEEL})

GOOD_LABELS = {
    Good.FOOD: "粮食",
    Good.COAL: "煤炭",
    Good.IRON_ORE: "铁矿石",
    Good.STEEL: "钢铁",
    Good.BRICK: "砖头",
    Good.CLOTH: "纺织品",
    Good.FERTILIZER: "化肥",
    Good.MACHINERY: "机械",
    Good.BUILDING: "建筑",
    Good.SERVICE: "服务",
}
