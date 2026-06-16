from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        raise NotImplementedError


class ClaudeProvider(LLMProvider):
    def generate(self, prompt: str) -> str:
        # TODO: connect Anthropic API
        return "Claude placeholder response"


class OpenAIProvider(LLMProvider):
    def generate(self, prompt: str) -> str:
        # TODO: connect OpenAI API
        return "OpenAI placeholder response"
