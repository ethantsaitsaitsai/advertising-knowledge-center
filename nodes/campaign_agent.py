from langchain.agents import create_agent
from config.llm import llm
from tools.campaign_tool import query_campaign_data
from tools.search_db import search_ambiguous_term
from datetime import datetime, timedelta
from prompts.campaign_agent_prompt import CAMPAIGN_AGENT_SYSTEM_PROMPT_TEMPLATE

def create_campaign_agent():
    """
    Creates the Campaign Agent using the new create_agent function.
    """
    tools = [query_campaign_data, search_ambiguous_term]
    
    # Dynamic Date Context
    now = datetime.now()
    this_year_start = f"{now.year}-01-01"
    this_year_end = now.strftime("%Y-%m-%d")
    last_year = now.year - 1
    last_year_start = f"{last_year}-01-01"
    last_year_end = f"{last_year}-12-31"
    
    date_context = f"""- 今天日期: {now.strftime('%Y-%m-%d')}
- 今年 (This Year): {this_year_start} 到 {this_year_end}
- 去年 (Last Year): {last_year_start} 到 {last_year_end}"""

    system_prompt = CAMPAIGN_AGENT_SYSTEM_PROMPT_TEMPLATE.format(current_date_context=date_context)
    
    # Use the new create_agent API
    agent = create_agent(model=llm, tools=tools, system_prompt=system_prompt)
    return agent