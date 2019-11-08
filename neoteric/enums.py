from enum import Enum
Board = Enum('Board', [('PASSAGE', 0), ('RIGID', 1), ('WOOD', 2), ('BOMB', 3), ('FLAMES', 4), ('FOG', 5), 
                       ('POWER_BOMB', 6), ('POWER_RANGE', 7), ('POWER_KICK', 8), ('AGENTDUMMY', 9), 
                       ('AGENT0', 10), ('AGENT1', 11), ('AGENT2', 12), ('AGENT3', 13)])
Action = Enum('Action', [('STOP', 0), ('UP', 1), ('DOWN', 2), ('LEFT', 3), ('RIGHT', 4), ('BOMB', 5)])
Direction = Enum('Direction', [('UP', (-1, 0)), ('LEFT', (0, -1)), ('DOWN', (1, 0)), ('RIGHT', (0, 1))])
SensorType = Enum('SensorType', [('ABSTRACT', 0), ('TREE', 1), ('GRAPH', 2), ('TRANSCEIVER', 3), ('KERNEL', 4), ('BOMB', 5), 
                                 ('NETWORK', 6)]) 
ControlType = Enum('ControlType', [('SAFETY', 0), ('DEMOLISH', 1), ('COLLECT', 2), ('REPEL', 3), ('KICK', 4), ('EXPLORE', 5)])