"""
Initialize the JSON data store from Excel
Run this once to convert your Excel file to JSON format
"""
from data_store import get_store

if __name__ == "__main__":
    print("=" * 60)
    print("PSUR Schedule - Excel to JSON Converter")
    print("=" * 60)
    print()
    
    store = get_store()
    
    print(f"✅ Data loaded successfully!")
    print(f"   Total records: {len(store.data)}")
    print()
    
    stats = store.get_stats()
    print("📊 Statistics:")
    print(f"   Overdue: {stats['overdue']}")
    print(f"   Due soon (30 days): {stats['due_soon']}")
    print()
    
    print("📋 By Status:")
    for status, count in sorted(stats['by_status'].items(), key=lambda x: x[1], reverse=True):
        print(f"   {status}: {count}")
    print()
    
    print("🏷️  By Class:")
    for classification, count in sorted(stats['by_class'].items()):
        print(f"   {classification}: {count}")
    print()
    
    print("✍️  By Writer:")
    for writer, count in sorted(stats['by_writer'].items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"   {writer}: {count}")
    
    if len(stats['by_writer']) > 10:
        print(f"   ... and {len(stats['by_writer']) - 10} more")
    
    print()
    print("=" * 60)
    print("✅ JSON data store is ready!")
    print(f"   Data file: {store.JSON_DATA_PATH}")
    print(f"   Metadata: {store.METADATA_PATH}")
    print()
    print("Next steps:")
    print("1. Start the server: uvicorn server:app --reload")
    print("2. Open http://localhost:8000")
    print("3. Updates will now show live in the UI!")
    print("=" * 60)
