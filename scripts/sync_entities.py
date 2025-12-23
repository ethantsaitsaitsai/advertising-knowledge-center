import sys
import os
from tqdm import tqdm
import uuid

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import get_mysql_db
from utils.rag_service import RagService
from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer
from httpx import ConnectTimeout, ConnectError

def fetch_data_from_mysql():
    db = get_mysql_db()
    entities = []

    print("📥 Fetching Brands (clients.product)...")
    from sqlalchemy import text
    
    with db._engine.connect() as connection:
        # 1. Brands
        result = connection.execute(text("SELECT DISTINCT product, id FROM clients WHERE product IS NOT NULL AND product != ''"))
        for row in result:
            entities.append({
                "text": row[0],
                "type": "brands",
                "table": "clients",
                "column": "product",
                "sql_id": row[1]
            })
            
        # 2. Advertisers
        print("📥 Fetching Advertisers (clients.company)...")
        result = connection.execute(text("SELECT DISTINCT company, id FROM clients WHERE company IS NOT NULL AND company != ''"))
        for row in result:
            entities.append({
                "text": row[0],
                "type": "advertisers", 
                "table": "clients",
                "column": "company",
                "sql_id": row[1]
            })

        # 3. Agencies
        print("📥 Fetching Agencies (agency.agencyname)...")
        result = connection.execute(text("SELECT DISTINCT agencyname, id FROM agency WHERE agencyname IS NOT NULL AND agencyname != ''"))
        for row in result:
            entities.append({
                "text": row[0],
                "type": "agencies",
                "table": "agency",
                "column": "agencyname",
                "sql_id": row[1]
            })

        # 4. Campaigns
        print("📥 Fetching Campaigns (cue_lists.campaign_name)...")
        result = connection.execute(text("SELECT DISTINCT campaign_name, id FROM cue_lists WHERE campaign_name IS NOT NULL AND campaign_name != ''"))
        for row in result:
            entities.append({
                "text": row[0],
                "type": "campaign_names", 
                "table": "cue_lists",
                "column": "campaign_name",
                "sql_id": row[1]
            })

        # 5. Industries
        print("📥 Fetching Industries (pre_campaign_categories.name)...")
        result = connection.execute(text("SELECT DISTINCT name, id FROM pre_campaign_categories WHERE name IS NOT NULL AND name != ''"))
        for row in result:
            entities.append({
                "text": row[0],
                "type": "industries",
                "table": "pre_campaign_categories",
                "column": "name",
                "sql_id": row[1]
            })

        # 6. Keywords
        print("📥 Fetching Keywords (target_segments where data_source='keyword')...")
        result = connection.execute(text("SELECT DISTINCT data_value, id FROM target_segments WHERE data_source='keyword' AND data_value IS NOT NULL AND data_value != ''"))
        for row in result:
            entities.append({
                "text": row[0],
                "type": "keywords",
                "table": "target_segments",
                "column": "data_value",
                "sql_id": row[1]
            })

        # 7. Sub-Industries
        print("📥 Fetching Sub-Industries (pre_campaign_sub_categories.name)...")
        result = connection.execute(text("SELECT DISTINCT name, id FROM pre_campaign_sub_categories WHERE name IS NOT NULL AND name != ''"))
        for row in result:
            entities.append({
                "text": row[0],
                "type": "sub_industries",
                "table": "pre_campaign_sub_categories",
                "column": "name",
                "sql_id": row[1]
            })

    print(f"✅ Total entities fetched: {len(entities)}")
    return entities

def sync_to_qdrant():
    # Configuration
    COLLECTION_NAME = "AKC1128"
    HOST = os.getenv("QDRANT_HOST", "34.80.206.199")
    PORT = int(os.getenv("QDRANT_PORT", 6333))

    # Initialize
    print(f"🔌 Connecting to Qdrant at {HOST}:{PORT}...")
    try:
        client = QdrantClient(host=HOST, port=PORT, timeout=10)
        # Test connection
        client.get_collections()
    except (ConnectTimeout, ConnectError, Exception) as e:
        print(f"❌ Failed to connect to Qdrant: {e}")
        print("⚠️ Please check your network connection, VPN, or firewall settings.")
        return

    model = SentenceTransformer('intfloat/multilingual-e5-base')

    # Check if collection exists, if not create it
    collections = client.get_collections().collections
    exists = any(c.name == COLLECTION_NAME for c in collections)
    
    if not exists:
        print(f"🔨 Creating collection '{COLLECTION_NAME}'...")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE)
        )
    else:
        print(f"ℹ️ Collection '{COLLECTION_NAME}' already exists. Appending/Updating data...")

    # Fetch Data
    try:
        entities = fetch_data_from_mysql()
    except Exception as e:
        print(f"❌ Failed to fetch data from MySQL: {e}")
        return

    # Batch Process
    BATCH_SIZE = 64
    
    print("🚀 Starting Upsert Process...")
    
    # Use a simple loop for batching
    for i in tqdm(range(0, len(entities), BATCH_SIZE), desc="Upserting Batches"):
        batch = entities[i:i + BATCH_SIZE]
        
        # Prepare texts for embedding
        texts_to_embed = []
        for e in batch:
            cleaned = RagService.clean_text(e["text"])
            texts_to_embed.append(cleaned if cleaned else e["text"])
            
        embeddings = model.encode(texts_to_embed)
        
        batch_points = []
        for j, entity in enumerate(batch):
            # Generate a deterministic UUID
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{entity['type']}_{entity['sql_id']}"))
            
            batch_points.append(models.PointStruct(
                id=point_id,
                vector=embeddings[j].tolist(),
                payload={
                    "text": entity["text"],
                    "type": entity["type"],
                    "table": entity["table"],
                    "column": entity["column"],
                    "sql_id": entity["sql_id"]
                }
            ))
            
        try:
            client.upsert(
                collection_name=COLLECTION_NAME,
                points=batch_points
            )
        except Exception as e:
            print(f"❌ Error upserting batch {i}: {e}")

    print("✅ Sync Complete!")

if __name__ == "__main__":
    sync_to_qdrant()