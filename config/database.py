import os
import traceback
import paramiko
from sqlalchemy import create_engine, MetaData
from langchain_community.utilities import SQLDatabase
from dotenv import load_dotenv
import clickhouse_connect
from sshtunnel import SSHTunnelForwarder

if not hasattr(paramiko, "DSSKey"):
    paramiko.DSSKey = paramiko.RSAKey

load_dotenv()

_mysql_db_instance = None
_ssh_tunnel = None


def get_mysql_db():
    global _mysql_db_instance, _ssh_tunnel
    if _mysql_db_instance is None:
        print("🔌 Initializing MySQL connection...")
        try:
            db_user = os.getenv('DB_USER')
            db_password = os.getenv('DB_PASSWORD')
            db_name = os.getenv('DB_NAME')
            db_host = os.getenv('DB_HOST')
            db_port = int(os.getenv('DB_PORT', 3306))

            # SSH Connection details
            ssh_host = os.getenv('SSH_HOST')
            ssh_port = int(os.getenv('SSH_PORT', 22))
            ssh_user = os.getenv('SSH_USER')
            ssh_password = os.getenv('SSH_PASSWORD')

            print(f"🛡️  Establishing SSH Tunnel to {ssh_host}...")

            ssh_args = {
                "ssh_address_or_host": (ssh_host, ssh_port),
                "ssh_username": ssh_user,
                "remote_bind_address": (db_host, db_port),
                "ssh_password": ssh_password,
                "set_keepalive": 30.0, # Send keepalive packets every 30 seconds
            }

            _ssh_tunnel = SSHTunnelForwarder(**ssh_args)
            _ssh_tunnel.start()

            print(f"✅ SSH Tunnel established! Local bind port: {_ssh_tunnel.local_bind_port}")

            # Override host and port to use the tunnel
            current_host = "127.0.0.1"
            current_port = _ssh_tunnel.local_bind_port

            db_uri = (
                f"mysql+mysqlconnector://{db_user}:{db_password}"
                f"@{current_host}:{current_port}/{db_name}"
            )

            # Add connection pooling settings
            engine = create_engine(
                db_uri,
                pool_recycle=3600,  # Recycle connections every hour
                pool_pre_ping=True,  # Check connection before usage (Auto-reconnect)
                connect_args={'consume_results': True} # Ensure previous results are consumed
            )
            target_tables = [
                "cue_lists",
                "one_campaigns",
                "clients",
                "agency",
                "cue_list_budgets",
                "cue_list_ad_formats",
                "ad_format_types",
                "pricing_models",
                "pre_campaign",
                "campaign_target_pids",
                "target_segments",
                "segment_categories"
            ]
            metadata = MetaData()
            metadata.reflect(bind=engine, only=target_tables, resolve_fks=False)
            _mysql_db_instance = SQLDatabase(
                engine=engine,
                metadata=metadata,
                include_tables=target_tables,
                lazy_table_reflection=True
            )

        except Exception as e:
            print("❌ Detailed Error Traceback:")
            traceback.print_exc()
            if _ssh_tunnel:
                _ssh_tunnel.stop()
                _ssh_tunnel = None
            raise ValueError(
                "Error: Could not establish MySQL connection (possibly via SSH). "
                "Please check your .env configuration."
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
