from schemas.state import GraphState
from config.llm import llm
from config.database import db
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage

def sql_generator_node(state: GraphState) -> GraphState:
    """
    Generates the final SQL query based on the user's question and clarified terms.
    """
    print("---SQL GENERATOR---")
    messages = state["messages"]
    clarified_terms = state.get("clarified_terms", {})
    
    # Get the latest user question
    user_question = ""
    for msg in reversed(messages):
        if msg.type == "human":
            user_question = msg.content
            break

    # Get the database schema
    schema = db.get_table_info()

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a master SQL writer. Your task is to generate a syntactically correct {dialect} query based on the user's question and the provided schema.
        You have been given a set of clarified terms that have already been verified. Use these clarified terms in your query.
        - Your final output must be only the raw SQL query string. Do not include any other text, explanations, or markdown formatting.
        - Always use the exact values from the 'Clarified Terms' in your WHERE clauses.
        - Do not generate any DML statements (INSERT, UPDATE, DELETE, DROP, etc.).
        - Ensure the query is as simple and efficient as possible.
        """),
        ("user", "Database Schema:\n{schema}\n\nUser's Question: {question}\n\nClarified Terms: {clarified_terms}\n\nSQL Query:")
    ])

    chain = prompt | llm

    try:
        response = chain.invoke({
            "dialect": db.dialect,
            "schema": schema,
            "question": user_question,
            "clarified_terms": str(clarified_terms)
        })
        
        # Clean up the response to get only the SQL
        sql_query = response.content.strip().replace("```sql", "").replace("```", "").strip()
        
        print(f"Generated SQL: {sql_query}")
        # The final output of this node is the SQL query, which we add as a new AIMessage
        messages.append(AIMessage(content=sql_query))
        return {"messages": messages}
    except Exception as e:
        error_message = f"Error generating SQL: {e}"
        print(error_message)
        messages.append(AIMessage(content=f"Error: {error_message}"))
        return {"messages": messages}

