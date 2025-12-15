from tools.search_db import search_ambiguous_term

if __name__ == "__main__":
    try:
        results = search_ambiguous_term.invoke("悠遊卡")
        print("\nSearch Results:")
        for r in results:
            print(r)
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
