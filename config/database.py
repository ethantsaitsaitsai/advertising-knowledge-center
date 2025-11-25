import os
from langchain_community.utilities import SQLDatabase
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

_mysql_db_instance = None


def get_mysql_db():
    global _mysql_db_instance
    if _mysql_db_instance is None:
        print("🔌 Initializing MySQL connection...")
        try:
            db_uri = (
                f"mysql+mysqlconnector://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
                f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
            )
            _mysql_db_instance = SQLDatabase.from_uri(
                db_uri,
                include_tables=[
                    "cuelist",
                    "one_campaigns",
                    "pre_campaign",
                    "campaign_target_pids",
                    "target_segments",
                    "segment_categories"
                ]
            )
        except Exception as e:
            raise ValueError(
                "Error: Could not establish MySQL connection. "
                "Please check if DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME are set and correct in .env file."
            ) from e
    return _mysql_db_instance


# ClickHouse Connection
_ch_db_instance = None


def get_clickhouse_db():
    global _ch_db_instance
    if _ch_db_instance is None:
        print("🔌 Initializing ClickHouse HTTPS connection...")
        try:
            _ch_db_instance = clickhouse_connect.get_client(
                host=os.getenv('CH_DB_HOST'),
                port=int(os.getenv('CH_DB_PORT')),
                secure=True,
                verify=False,
                username=os.getenv('CH_DB_USER'),
                password=os.getenv('CH_DB_PASSWORD'),
                database=os.getenv('CH_DB_NAME'),
            )
        except Exception as e:
            raise ValueError(
                f"Error: Could not establish ClickHouse HTTPS connection: {e}"
            )
    return _ch_db_instance


def test_mysql_connection():
    """
    Tests the MySQL database connection by executing a simple query.
    """
    print("\n--- Testing MySQL Connection ---")
    try:
        db = get_mysql_db()
        # The .run() method executes and fetches results.
        result = db.run("SELECT 1")
        # The result from langchain's SQLDatabase.run is a string, e.g., "[(1,)]"
        if "1" in result:
            print("✅ MySQL connection successful!")
        else:
            print(f"❌ MySQL test query failed. Result: {result}")
    except Exception as e:
        print(f"❌ MySQL connection failed: {e}")


def test_clickhouse_connection():
    """
    Tests the ClickHouse database connection by executing a simple query.
    """
    print("\n--- Testing ClickHouse Connection ---")
    try:
        client = get_clickhouse_db()
        result = client.query("SELECT 1")
        if result.result_rows == [(1,)]:
            print("✅ ClickHouse connection successful!")
        else:
            print(f"❌ ClickHouse test query failed. Result: {result.result_rows}")
    except Exception as e:
        print(f"❌ ClickHouse connection failed: {e}")


if __name__ == '__main__':
    test_mysql_connection()
    test_clickhouse_connection()
