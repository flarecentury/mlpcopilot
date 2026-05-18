"""
Pydantic models for FsExplorer agent actions.

This module defines the structured data models used to represent
the actions the agent can take during filesystem exploration.
"""

from pydantic import BaseModel, Field
from typing import TypeAlias, Literal, Any


# =============================================================================
# Type Aliases
# =============================================================================

Tools: TypeAlias = Literal[
    "read",
    "grep",
    "glob",
    "scan_folder",
    "preview_file",
    "parse_file",
    "semantic_search",
    "get_document",
    "list_indexed_documents",
]
"""Available tool names that the agent can invoke."""

ActionType: TypeAlias = Literal["stop", "godeeper", "toolcall", "askhuman"]
"""Types of actions the agent can take."""


# =============================================================================
# Action Models
# =============================================================================

class StopAction(BaseModel):
    """
    Action indicating the task is complete.
    
    Used when the agent has gathered enough information to provide
    a final answer to the user's query.
    """
    
    final_result: str = Field(
        description="Final result of the operation with the answer to the user's query"
    )


class AskHumanAction(BaseModel):
    """
    Action requesting clarification from the user.
    
    Used when the agent needs additional information or context
    to proceed with the task.
    """
    
    question: str = Field(
        description="Clarification question to ask the user"
    )


class GoDeeperAction(BaseModel):
    """
    Action to navigate into a subdirectory.
    
    Used when the agent needs to explore a subdirectory
    to find relevant files.
    """
    
    directory: str = Field(
        description="Path to the directory to navigate into"
    )


class ToolCallArg(BaseModel):
    """
    A single argument for a tool call.
    
    Represents a parameter name-value pair to pass to a tool.
    """
    
    parameter_name: str = Field(
        description="Name of the parameter"
    )
    parameter_value: Any = Field(
        description="Value for the parameter"
    )


class ToolCallAction(BaseModel):
    """
    Action to invoke a filesystem tool.
    
    Used when the agent needs to read files, search for patterns,
    or parse documents to gather information.
    """
    
    tool_name: Tools = Field(
        description="Name of the tool to invoke"
    )
    tool_input: list[ToolCallArg] = Field(
        description="Arguments to pass to the tool"
    )

    def to_fn_args(self) -> dict[str, Any]:
        """
        Convert tool input to a dictionary for function calls.
        
        Returns:
            Dictionary mapping parameter names to values.
        """
        return {arg.parameter_name: arg.parameter_value for arg in self.tool_input}


class Action(BaseModel):
    """
    Container for an agent action with reasoning.
    
    Wraps any of the specific action types (stop, go deeper,
    tool call, ask human) along with the agent's explanation
    for why this action was chosen.
    """
    
    action: ToolCallAction | GoDeeperAction | StopAction | AskHumanAction = Field(
        description="The specific action to take"
    )
    reason: str = Field(
        description="Explanation for why this action was chosen"
    )

    def to_action_type(self) -> ActionType:
        """
        Get the type of this action.
        
        Returns:
            The action type string: "toolcall", "godeeper", "askhuman", or "stop".
        """
        if isinstance(self.action, ToolCallAction):
            return "toolcall"
        elif isinstance(self.action, GoDeeperAction):
            return "godeeper"
        elif isinstance(self.action, AskHumanAction):
            return "askhuman"
        else:
            return "stop"
