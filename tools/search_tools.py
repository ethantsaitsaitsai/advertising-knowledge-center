import ast
from typing import List
from langchain_core.tools import tool
from config.database import db


@tool
def search_ambiguous_term(search_term: str, column_names: List[str]) -> List[str]:
    """
    Searches for an ambiguous term across multiple specified table columns using a LIKE query.
    Use this tool when a user's query contains a potential abbreviation, typo, or partial name
    for a value in the database (e.g., a company or brand name).

    Args:
        search_term: The ambiguous term provided by the user to search for.
        column_names: A list of column names to search within.

    Returns:
        A de-duplicated list of potential matching values found in the database.
    """
    all_matches = set()
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
                    all_matches.add(match_tuple[0])
        except Exception as e:
            # May fail if column doesn't exist or other SQL errors
            print(f"Error searching in column {column}: {e}")
            continue
    return list(all_matches)
