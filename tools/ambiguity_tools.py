import ast
from typing import List, Dict
from langchain_core.tools import tool
from config.database import db


@tool
def find_ambiguous_term_options(search_term: str, column_names: List[str]) -> List[Dict[str, str]]:
    """
    Searches for possible matches for an ambiguous term across specified database columns.
    Use this tool to find clarification options for a term you have identified as ambiguous.

    Args:
        search_term: The ambiguous term to search for.
        column_names: A list of column names to search within.

    Returns:
        A list of dictionaries, where each dictionary represents a potential match
        and contains the 'column' and 'value' of that match.
    """
    all_matches = set()  # Use a set of tuples to store (column, value) to avoid duplicates
    table_name = "test_cue_list"  # Assuming a single table for now
    for column in column_names:
        try:
            # Using f-string for table and column names is generally unsafe,
            # but here we control the table name and the LLM provides the column names
            # from a known schema. Parameters are handled safely by the db.run.
            query = f"SELECT DISTINCT `{column}` FROM `{table_name}` WHERE `{column}` LIKE :search_term"
            results_str = db.run(query, parameters={"search_term": f"%{search_term}%"})
            # The result from db.run is a string representation of a list of tuples, needs parsing.
            # e.g., "[('Result 1',), ('Result 2',)]"
            matches = ast.literal_eval(results_str)
            for match_tuple in matches:
                if match_tuple and isinstance(match_tuple, tuple):
                    all_matches.add((column, match_tuple[0]))  # Add a tuple to the set
        except Exception as e:
            # May fail if column doesn't exist or other SQL errors
            print(f"Error searching in column {column}: {e}")
            continue

    # Convert the set of tuples to a list of dictionaries
    return [{"column": col, "value": val} for col, val in all_matches]
