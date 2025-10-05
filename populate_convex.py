"""Populate Convex database with data from Excel file."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.db_convex import get_store
from backend.excel_utils import read_excel_auto, canon_record, PSUR_SCHEDULE_PATH

def populate_convex():
    """Load data from Excel and populate Convex database."""
    print("🚀 Starting Convex data population...")
    print(f"📁 Reading Excel file: {PSUR_SCHEDULE_PATH}")
    
    # Convert to Path object
    excel_path = Path(PSUR_SCHEDULE_PATH)
    
    # Check if Excel file exists
    if not excel_path.exists():
        print(f"❌ Excel file not found: {excel_path}")
        print("\nPlease ensure the Excel file is in the correct location:")
        print(f"   {excel_path}")
        return
    
    # Read Excel data
    try:
        df, colmap = read_excel_auto(str(excel_path))
        print(f"✅ Found {len(df)} records in Excel")
    except Exception as e:
        print(f"❌ Failed to read Excel file: {e}")
        return
    
    # Get Convex store
    store = get_store()
    
    # Check if Convex already has data
    existing = store.get_all()
    if existing:
        print(f"\n⚠️  Warning: Convex already has {len(existing)} records")
        response = input("Do you want to continue and add more records? (y/n): ")
        if response.lower() != 'y':
            print("❌ Cancelled")
            return
    
    # Convert DataFrame rows to canonical records and insert
    added = 0
    errors = 0
    
    print("\n📤 Uploading records to Convex...")
    
    for idx, row in df.iterrows():
        try:
            # Convert row to canonical record format
            record = canon_record(row, colmap)
            
            # Add to Convex
            td_number = store.add_record(record)
            added += 1
            
            if added % 10 == 0:
                print(f"  ✓ Uploaded {added}/{len(df)} records...")
                
        except Exception as e:
            errors += 1
            print(f"  ⚠️  Error adding record {idx}: {e}")
    
    # Final summary
    print("\n" + "="*60)
    print("✅ Convex Population Complete!")
    print(f"📊 Total records in Excel: {len(df)}")
    print(f"✓ Successfully uploaded: {added}")
    print(f"❌ Errors: {errors}")
    print("="*60)
    
    # Verify
    final_count = len(store.get_all())
    print(f"\n✓ Convex now has {final_count} total records")
    
    # Show sample
    if final_count > 0:
        print("\n📋 Sample records:")
        samples = store.get_all()[:3]
        for record in samples:
            td = record.get('td_number', 'N/A')
            product = record.get('product_name', 'N/A')
            writer = record.get('writer', 'N/A')
            due = record.get('due_date', 'N/A')
            print(f"  • {td}: {product} (Writer: {writer}, Due: {due})")
    
    print("\n🎉 Ready to use! Test with voice commands:")
    print("   'Show me all Class III items'")
    print("   'Who owns TD001?'")
    print("   'What's overdue?'")
    
    store.close()


if __name__ == "__main__":
    populate_convex()
