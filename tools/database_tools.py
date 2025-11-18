from langchain_community.agent_toolkits import SQLDatabaseToolkit
from config.database import db
from config.llm import llm # LLM is needed for SQLDatabaseToolkit

# Instantiate the SQLDatabaseToolkit
toolkit = SQLDatabaseToolkit(db=db, llm=llm)

# Get all standard SQL tools from the toolkit
database_tools = toolkit.get_tools()

# Extract specific tools for easier access if needed, or just use them from the list
sql_db_query_tool = next(tool for tool in database_tools if tool.name == "sql_db_query")
sql_db_schema_tool = next(tool for tool in database_tools if tool.name == "sql_db_schema")
sql_db_list_tables_tool = next(tool for tool in database_tools if tool.name == "sql_db_list_tables")
sql_db_query_checker_tool = next(tool for tool in database_tools if tool.name == "sql_db_query_checker")
