"""Migration script: SQLite → Convex Cloud"""
import asyncio
import sqlite3
from pathlib import Path

from backend.db_convex import get_store

SQLITE_PATH = Path(__file__).parent / "data" / "psur_schedule.db"


async def migrate():
    """Migrate data from SQLite to Convex."""
    print("🚀 Starting migration: SQLite → Convex")
    
    # Check if SQLite database exists
    if not SQLITE_PATH.exists():
        print(f"❌ SQLite database not found: {SQLITE_PATH}")
        print("ℹ️  No data to migrate. Convex will start fresh.")
        return
    
    # Connect to SQLite
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    
    # Get all records
    cursor.execute("SELECT * FROM psur_reports")
    rows = cursor.fetchall()
    print(f"📊 Found {len(rows)} records in SQLite")
    
    if not rows:
        print("ℹ️  No records to migrate.")
        sqlite_conn.close()
        return
    
    # Connect to Convex
    print(f"🔌 Connecting to Convex...")
    convex = get_store()
    
    # Migrate records
    print("📤 Migrating records...")
    migrated = 0
    errors = 0
    
    for row in rows:
        try:
            record = {
                "td_number": row['td_number'],
                "psur_number": row['psur_number'],
                "type": row['type'],
                "product_name": row['product_name'],
                "catalog_number": row['catalog_number'],
                "writer": row['writer'],
                "email": row['email'],
                "start_period": row['start_period'],
                "end_period": row['end_period'],
                "frequency": row['frequency'],
                "due_date": row['due_date'],
                "status": row['status'],
                "canada_needed": row['canada_needed'],
                "canada_status": row['canada_status'],
                "comments": row['comments'],
                "class": row['class'],
            }
            
            # Remove None values
            record = {k: v for k, v in record.items() if v is not None}
            
            await convex.add_record(record)
            migrated += 1
            
            if migrated % 10 == 0:
                print(f"  ✓ Migrated {migrated}/{len(rows)} records...")
                
        except Exception as e:
            errors += 1
            print(f"  ⚠️  Error migrating {row['td_number']}: {e}")
    
    # Verify
    stats = await convex.get_stats()
    
    # Close connections
    await convex.close()
    sqlite_conn.close()
    
    # Summary
    print("\n" + "="*60)
    print("✅ Migration Complete!")
    print(f"📊 Records migrated: {migrated}/{len(rows)}")
    print(f"❌ Errors: {errors}")
    print(f"✓ Convex total records: {stats.get('total_records', 0)}")
    print("="*60)
    
    if errors == 0:
        print("\n🎉 All records migrated successfully!")
        print("\nNext steps:")
        print("1. ✅ Database type already set to 'convex' in .env")
        print("2. Restart server: uvicorn main:app --reload")
        print("3. View data: https://dashboard.convex.dev/d/unique-heron-539")
    else:
        print(f"\n⚠️  Migration completed with {errors} error(s).")
        print("Review the errors above and re-run if needed.")


if __name__ == "__main__":
    asyncio.run(migrate())
