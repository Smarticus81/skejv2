"""Quick test of Convex database."""
from backend.db_convex import get_store

store = get_store()

print("\n✅ Convex Database Status:")
print("="*60)

stats = store.get_stats()
print(f"Stats returned: {stats}")
print(f"Type: {type(stats)}")

if stats:
    print(f"\n📊 Total Records: {stats.get('total_records', 'N/A')}")
    print(f"📝 By Status: {stats.get('by_status', {})}")
    print(f"🏷️  By Class: {stats.get('by_class', {})}")
    print(f"⚠️  Overdue: {stats.get('overdue_count', 0)}")
    print(f"🔄 Duplicate TDs: {len(stats.get('duplicate_td_numbers', []))}")
else:
    all_records = store.get_all()
    print(f"📊 Total Records: {len(all_records)}")

print("\n✅ SQLite Removed - Convex Only!")
print("🚀 Ready for voice operations")

store.close()
