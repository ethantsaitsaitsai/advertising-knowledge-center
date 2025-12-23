import os
from tools.entity_resolver import resolve_entity
from dotenv import load_dotenv
import json

def check():
    load_dotenv()
    print("🔍 Resolving '悠遊卡'...")
    res = resolve_entity.invoke({"keyword": "悠遊卡"})
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    check()
