"""
Pytest fixtures and mocks for FsExplorer tests.

Provides mock implementations of the Google GenAI client for unit testing
without making actual API calls.
"""

from google.genai.types import (
    HttpOptions,
    Content,
    GenerateContentResponse,
    Candidate,
    Part,
    GenerateContentResponseUsageMetadata,
)
from fs_explorer.models import StopAction, Action


class MockModels:
    """Mock implementation of the GenAI models interface."""
    
    async def generate_content(self, *args, **kwargs) -> GenerateContentResponse:
        """Return a mock response with a stop action."""
        return GenerateContentResponse(
            candidates=[
                Candidate(
                    content=Content(
                        role="model",
                        parts=[
                            Part.from_text(
                                text=Action(
                                    action=StopAction(
                                        final_result="this is a final result"
                                    ),
                                    reason="I am done",
                                ).model_dump_json()
                            )
                        ],
                    )
                )
            ],
            usage_metadata=GenerateContentResponseUsageMetadata(
                prompt_token_count=100,
                candidates_token_count=50,
                total_token_count=150,
            ),
        )


class MockAio:
    """Mock implementation of the async GenAI interface."""
    
    @property
    def models(self) -> MockModels:
        """Return mock models interface."""
        return MockModels()


class MockGenAIClient:
    """
    Mock implementation of the Google GenAI client.
    
    Provides predictable responses for testing without API calls.
    """
    
    def __init__(self, api_key: str, http_options: HttpOptions) -> None:
        """Initialize mock client (ignores parameters)."""
        pass

    @property
    def aio(self) -> MockAio:
        """Return mock async interface."""
        return MockAio()
