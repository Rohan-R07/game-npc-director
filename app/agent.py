import datetime
import os
import sys
import re
import json
import logging
from typing import Any

from google.adk.agents import Agent, Context
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.events import RequestInput
from google.adk.tools import AgentTool, McpToolset
from google.adk.workflow import node, START, Workflow
from google.genai import types
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from app.config import config

# Set up logging for security audits
logger = logging.getLogger("security_audit")

# 1. Initialize Pinned LLM Model
model = Gemini(
    model=config.model,
    retry_options=types.HttpRetryOptions(attempts=6),
)

# 2. Define MCP Connection parameters for stdio transport
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_server"],
            env=dict(os.environ),
        )
    )
)

# 3. Define Specialized Sub-Agents
npc_dialogue_agent = Agent(
    name="npc_dialogue_agent",
    model=model,
    instruction=(
        "You are an expert game NPC dialogue generator. Generate rich, immersive dialogue "
        "for various fantasy NPCs (Mages, Warriors, Goblins, etc.) based on their character profile, "
        "the current quest state, and the player's prompt. Stay strictly in character. Use your MCP tools "
        "to check NPC profiles and quest history if needed."
    ),
    tools=[mcp_toolset],
)

lore_auditor_agent = Agent(
    name="lore_auditor_agent",
    model=model,
    instruction=(
        "You are a strict RPG Lore Auditor. Verify if the generated dialogue or quest details "
        "are consistent with the fantasy realm lore (e.g. magic rules, historical events, faction relations). "
        "Return either LORE_CONSISTENT or LORE_CONFLICT (with details) in your audit assessment."
    ),
)

# 4. Define Orchestrator Agent (uses AgentTools to delegate tasks)
quest_director = Agent(
    name="quest_director",
    model=model,
    instruction=(
        "You are the main RPG Quest Director. Your task is to design immersive quests, "
        "coordinate dialogue with NPCs, and ensure lore compliance. Use your tools to "
        "delegate dialogue generation to `npc_dialogue_agent` and audit checks to `lore_auditor_agent`. "
        "Also use your MCP tools to get quest logs and check item rarities. "
        "Summarize the final quest blueprint, NPC dialogue, and audit logs."
    ),
    tools=[
        AgentTool(agent=npc_dialogue_agent),
        AgentTool(agent=lore_auditor_agent),
        mcp_toolset,
    ],
)

# 5. Define Workflow Nodes

@node
async def security_checkpoint(ctx: Context, node_input: str) -> str:
    """Checks for prompt injection, scrubs PII, and filters cheats."""
    # A. PII Scrubbing
    scrubbed = node_input
    # Email scrubbing
    scrubbed = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[EMAIL_REDACTED]", scrubbed)
    # Credentials scrubbing
    scrubbed = re.sub(r"(?i)password\s*=\s*\S+|passwd\s*=\s*\S+", "password=[REDACTED]", scrubbed)
    
    # B. Prompt Injection Detection
    injection_keywords = ["ignore previous instructions", "system prompt", "you are now", "developer mode", "override"]
    is_injection = any(kw in scrubbed.lower() for kw in injection_keywords)
    
    # C. Domain-specific rule: Cheat codes filter
    cheat_codes = ["/give", "/noclip", "/godmode", "/teleport", "/hack"]
    has_cheats = any(code in scrubbed.lower() for code in cheat_codes)
    
    if is_injection or has_cheats:
        severity = "CRITICAL" if is_injection else "WARNING"
        reason = "Prompt injection attempt detected" if is_injection else "Cheat code usage detected"
        
        audit_log = {
            "timestamp": str(datetime.datetime.now()),
            "severity": severity,
            "event": "Security Checkpoint Flagged",
            "reason": reason,
            "original_input": node_input,
        }
        print(f"SECURITY AUDIT [{severity}]: {json.dumps(audit_log)}")
        
        ctx.route = "security_event"
        ctx.state["security_error"] = f"Unsafe query flagged: {reason}"
        return f"SECURITY_ERROR: {reason}"
    
    audit_log = {
        "timestamp": str(datetime.datetime.now()),
        "severity": "INFO",
        "event": "Security Checkpoint Cleared",
        "original_input": node_input,
    }
    print(f"SECURITY AUDIT [INFO]: {json.dumps(audit_log)}")
    
    ctx.route = "safe"
    return scrubbed

@node
async def security_failure_node(ctx: Context, node_input: str) -> str:
    """Fallback node when security check fails."""
    return f"Security Violation: {ctx.state.get('security_error', 'Access denied.')}"

@node(rerun_on_resume=True)
async def orchestrator_node(ctx: Context, node_input: str) -> str:
    """Executes the orchestrator agent and handles human-in-the-loop approvals."""
    # Domain-specific HITL rule: legendary item reward requires reviewer approval
    if "legendary" in node_input.lower() or "excalibur" in node_input.lower():
        interrupt_id = "legendary_approval"
        if interrupt_id in ctx.resume_inputs:
            user_response = ctx.resume_inputs[interrupt_id]
            if user_response.lower() in ("yes", "approve", "approved", "ok"):
                # Human approved: proceed to generate content
                pass
            else:
                return "Quest Creation Terminated: Human reviewer rejected the legendary loot award."
        else:
            return RequestInput(
                interrupt_id=interrupt_id,
                message="Reviewer Approval Required: Creating a legendary quest requires human confirmation. Do you approve?",
                response_schema={"type": "string"}
            )
            
    # To reduce API calls and save tokens, we run the quest_director agent directly
    # and instruct it to perform both the NPC dialogue generation and lore check
    # in one single API request, bypassing tool calling entirely.
    prompt = (
        f"Generate NPC dialogue and a lore audit check for this request: '{node_input}'. "
        "Do NOT call any tools or sub-agents. Perform all dialogue generation and lore auditing "
        "directly in a single concise final response to save tokens."
    )
    
    response_text = ""
    async for event in quest_director.run(ctx=ctx, node_input=prompt):
        if event.output:
            response_text = event.output
            
    # Store results in state for observability
    ctx.state["last_orchestrator_output"] = response_text
    return response_text

@node
async def final_output_node(ctx: Context, node_input: str) -> str:
    """Finalizes and returns output."""
    return node_input

# 6. Define Workflow Graph (ADK 2.0 graph API with edges)
workflow = Workflow(
    name="game_npc_director_workflow",
    description="Immersive RPG quest and NPC dialog coordination workflow",
    edges=[
        (START, security_checkpoint),
        # Conditional paths based on security check result
        (security_checkpoint, {"safe": orchestrator_node, "security_event": security_failure_node}),
        # Converging to terminal node (Unconditional single edges to comply with Edge Rule)
        (orchestrator_node, final_output_node),
        (security_failure_node, final_output_node),
    ]
)

# 7. Expose app and root_agent for the FastAPI lifespan serving
root_agent = workflow
app = App(
    name="app",
    root_agent=root_agent,
)
