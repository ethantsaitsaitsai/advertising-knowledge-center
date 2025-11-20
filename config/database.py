import os
from langchain_community.utilities import SQLDatabase
from dotenv import load_dotenv

load_dotenv()

try:
    db_uri = (
        f"mysql+mysqlconnector://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )
except Exception as e:
    raise ValueError(
        "Error: Could not read full database connection info from .env file. "
        "Please check if DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME are set."
    ) from e

db = SQLDatabase.from_uri(db_uri, include_tables=["cuelist",
                                                  "one_campaigns",
                                                  "pre_campaign",
                                                  "campaign_target_pids",
                                                  "target_segments"])
