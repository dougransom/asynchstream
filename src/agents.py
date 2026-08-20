import asyncio
from typing import Any, Callable, ParamSpec, TypeVar
from google.antigravity import Agent, LocalAgentConfig
from google.antigravity.hooks import policy

P = ParamSpec("P")
R = TypeVar("R")

def TraceableAction(name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Metaprogramming wrapper that intercepts and logs agent tool execution."""
    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Target-state selection prior to execution
            log_prefix = f"[AGENT-TRACE:{name}]" if name else "[AGENT-TRACE]"
            print(f"{log_prefix} Executing {fn.__name__}...")
            
            return await fn(*args, **kwargs) # type: ignore[return-value]
        return wrapper # type: ignore[return-value]
    return decorator


class AgentRegistryMeta(type):
    """Metaclass that auto-registers agent skills and enforces execution invariants."""
    def __new__(cls, name: str, bases: tuple[type, ...], attrs: dict[str, Any]):
        new_cls = super().__new__(cls, name, bases, attrs)
        if name != "BaseAgentSkill":
            handler = getattr(new_cls, "execute", None)
            if not callable(handler):
                raise TypeError(f"Skill {name} must implement an executable 'execute' method.")
        return new_cls


class BaseAgentSkill(metaclass=AgentRegistryMeta):
    pass


class ComplianceAgent(BaseAgentSkill):
    @TraceableAction(name="SafetyCheck")
    async def execute(self, prompt: str) -> str:
        # State selection pattern: Evaluate policy handler first
        strict_mode = True
        active_policy = policy.deny("*") if strict_mode else policy.allow_all()
        
        config = LocalAgentConfig(
            system_instructions="You are a strict compliance agent.",
            policies=[active_policy, policy.allow("view_file")],
        )
        
        async with Agent(config) as agent:
            response = await agent.chat(prompt)
            return await response.text()


if __name__ == "__main__":
    agent = ComplianceAgent()
    result = asyncio.run(agent.execute("Check project safety."))
    print(result)
