from langchain_community.agent_toolkits import SQLDatabaseToolkit
from config.database import db
from config.llm import llm

toolkit = SQLDatabaseToolkit(db=db, llm=llm)
sql_tools = toolkit.get_tools()
