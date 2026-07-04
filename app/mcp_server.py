from mcp.server.fastmcp import FastMCP

mcp = FastMCP("rpg-game-npc-director")

@mcp.tool()
def get_npc_profile(npc_name: str) -> str:
    """Get the character lore profile and personality traits for a fantasy NPC.
    
    Args:
        npc_name: The name of the NPC (e.g. Eldrin, Valerius, Grimnak).
    """
    profiles = {
        "eldrin": "Eldrin the Archmage. Age: 120. Specializes in Arcane and Frost magic. Wise, speaks formally, cautious about dark arts.",
        "valerius": "Sir Valerius. Champion of the Realm. Brave, honorable, loyal, speaks with chivalrous pride, hates goblins.",
        "grimnak": "Grimnak the Goblin Shaman. Shifty, speaks in broken English with frequent cackles, obsessed with shiny trinkets."
    }
    return profiles.get(npc_name.lower(), f"Unknown NPC: {npc_name}. Generate a basic background of a mysterious traveler.")

@mcp.tool()
def get_quest_log() -> str:
    """Get the active and completed quest history of the campaign."""
    return (
        "1. Active: [The Lost Relic of Eldrin] - Retrieve the Froststone from the goblin caverns.\n"
        "2. Completed: [Sir Valerius's Shield] - Found and returned Sir Valerius's shield from the dark forest."
    )

@mcp.tool()
def check_item_rarity(item_name: str) -> str:
    """Checks the rarity and attributes of loot items.
    
    Args:
        item_name: The name of the item.
    """
    items = {
        "froststone": "Loot Rarity: Epic. Type: Magic Artifact. Enables frost conjuring.",
        "excalibur": "Loot Rarity: Legendary. Type: Sword. Holy damage bonus.",
        "goblin key": "Loot Rarity: Common. Type: Key. Opens cavern gates."
    }
    return items.get(item_name.lower(), f"Loot Rarity: Common. Type: Standard Item. Item details for '{item_name}' unknown.")

if __name__ == "__main__":
    mcp.run(transport="stdio")
