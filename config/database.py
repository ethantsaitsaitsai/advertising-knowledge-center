import os
from langchain_community.utilities import SQLDatabase
from dotenv import load_dotenv
from clickhouse_driver import Client

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
                                                  "target_segments",
                                                  "segment_categories"])

# ClickHouse Connection
_ch_db_instance = None


def get_clickhouse_db():
    global _ch_db_instance
    if _ch_db_instance is None:
        print("🔌 Initializing ClickHouse connection...")
        try:
            _ch_db_instance = Client(
                host=os.getenv('CH_DB_HOST'),
                port=os.getenv('CH_DB_PORT'),
                user=os.getenv('CH_DB_USER'),
                password=os.getenv('CH_DB_PASSWORD'),
                database=os.getenv('CH_DB_NAME')
            )
        except Exception as e:
            raise ValueError(
                "Error: Could not establish ClickHouse connection. "
                "Please check if CH_DB_USER, CH_DB_PASSWORD, CH_DB_HOST, CH_DB_PORT, CH_DB_NAME are set and correct."
            ) from e
    return _ch_db_instance
