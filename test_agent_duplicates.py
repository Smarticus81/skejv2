"""Comprehensive duplicate TD test including API endpoints"""
import asyncio
from backend.db_store import get_store
from backend.server import tool_entry

async def test_agent_duplicate_creation():
    """Test creating duplicate TDs via the agent's tool interface"""
    
    print("="*70)
    print("COMPREHENSIVE DUPLICATE TD NUMBER TEST")
    print("="*70)
    
    store = get_store()
    
    # Clean up any existing test data
    print("\n🧹 Cleaning up any existing TD888 records...")
    store.delete_record("TD888")
    
    # Test 1: Direct store.add_record
    print("\n📌 TEST 1: Direct store.add_record() with duplicate TDs")
    print("-" * 70)
    
    record1 = {
        "td_number": "TD888",
        "psur_number": "PSUR888A",
        "product_name": "Product Alpha",
        "writer": "Alice",
        "class": "IIa",
        "status": "Assigned"
    }
    
    record2 = {
        "td_number": "TD888",  # Same TD
        "psur_number": "PSUR888B",
        "product_name": "Product Beta",
        "writer": "Bob",
        "class": "IIb",
        "status": "Assigned"
    }
    
    try:
        td1 = store.add_record(record1)
        print(f"   ✅ Created first record: {td1}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return
    
    try:
        td2 = store.add_record(record2)
        print(f"   ✅ Created second record with duplicate TD: {td2}")
    except Exception as e:
        print(f"   ❌ Failed to create duplicate: {e}")
        print(f"   🔍 Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return
    
    # Verify both exist
    all_td888 = store.find_all_by_td("TD888")
    print(f"\n   📊 Total TD888 records in database: {len(all_td888)}")
    for i, rec in enumerate(all_td888, 1):
        print(f"      {i}. {rec['product_name']} (PSUR: {rec['psur_number']}, Writer: {rec['writer']})")
    
    # Test 2: Via agent tool (add_psur_item)
    print("\n📌 TEST 2: Via agent's add_psur_item tool")
    print("-" * 70)
    
    tool_payload = {
        "name": "add_psur_item",
        "args": {
            "td_number": "TD888",  # Explicit duplicate
            "psur_number": "PSUR888C",
            "product_name": "Product Gamma",
            "writer": "Charlie",
            "class": "III",
            "status": "Assigned"
        }
    }
    
    try:
        result = await tool_entry(tool_payload)
        if "ok" in result and result["ok"]:
            print(f"   ✅ Agent tool created record: {result.get('td_number')}")
        else:
            print(f"   ❌ Agent tool failed: {result}")
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        import traceback
        traceback.print_exc()
    
    # Final verification
    all_td888 = store.find_all_by_td("TD888")
    print(f"\n   📊 Total TD888 records after agent tool: {len(all_td888)}")
    for i, rec in enumerate(all_td888, 1):
        print(f"      {i}. {rec['product_name']} (PSUR: {rec['psur_number']}, Writer: {rec['writer']})")
    
    # Test 3: Check stats
    print("\n📌 TEST 3: Database statistics")
    print("-" * 70)
    stats = store.get_stats()
    print(f"   Total records: {stats['total_records']}")
    print(f"   Duplicate TD numbers: {stats['duplicate_td_numbers']}")
    
    # Cleanup
    print("\n🧹 Cleaning up test data...")
    deleted = store.delete_record("TD888")
    print(f"   Deleted TD888: {deleted}")
    
    remaining = store.find_all_by_td("TD888")
    print(f"   Remaining TD888 records: {len(remaining)}")
    
    print("\n" + "="*70)
    print("✅ ALL TESTS COMPLETED")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(test_agent_duplicate_creation())
