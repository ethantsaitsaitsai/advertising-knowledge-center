
from langchain.agents import create_agent # Updated import
from config.llm import llm
from tools.performance_tool import query_performance_data
from prompts.performance_agent_prompt import PERFORMANCE_AGENT_SYSTEM_PROMPT

def create_performance_agent():
    """
    Creates the Performance Agent using the new create_agent function.
    """
    tools = [query_performance_data]
    
    # Use the new create_agent API
    agent = create_agent(model=llm, tools=tools, system_prompt=PERFORMANCE_AGENT_SYSTEM_PROMPT)
    return agent
