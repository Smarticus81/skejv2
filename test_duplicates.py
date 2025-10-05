"""Test duplicate TD number insertion"""
from backend.db_store import get_store

store = get_store()

# Test adding duplicate TD numbers
test_record_1 = {
    "td_number": "TD999",
    "psur_number": "PSUR999",
    "product_name": "Test Product A",
    "writer": "Test Writer",
    "status": "Test",
    "class": "IIa"
}

test_record_2 = {
    "td_number": "TD999",  # Same TD number
    "psur_number": "PSUR998",
    "product_name": "Test Product B",
    "writer": "Test Writer",
    "status": "Test",
    "class": "IIb"
}

print("Testing duplicate TD number insertion...")
print("\n1. Adding first record with TD999...")
try:
    result1 = store.add_record(test_record_1)
    print(f"   ✅ Success: {result1}")
except Exception as e:
    print(f"   ❌ Failed: {e}")

print("\n2. Adding second record with TD999 (duplicate)...")
try:
    result2 = store.add_record(test_record_2)
    print(f"   ✅ Success: {result2}")
except Exception as e:
    print(f"   ❌ Failed: {e}")

print("\n3. Retrieving all TD999 records...")
duplicates = store.find_all_by_td("TD999")
print(f"   Found {len(duplicates)} records:")
for i, rec in enumerate(duplicates, 1):
    print(f"   {i}. {rec.get('product_name')} - PSUR: {rec.get('psur_number')}")

print("\n4. Checking duplicate stats...")
stats = store.get_stats()
print(f"   Duplicate TD numbers: {stats.get('duplicate_td_numbers')}")

print("\n5. Cleaning up test records...")
deleted = store.delete_record("TD999")
print(f"   Deleted: {deleted}")

print("\n✅ Test complete!")
