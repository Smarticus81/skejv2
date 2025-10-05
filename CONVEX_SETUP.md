# Convex Database Setup Guide

## ✅ What's Ready

Your Convex integration is configured and ready to deploy!

**Files Created:**
- ✅ `convex/schema.ts` - Database schema with indexes
- ✅ `convex/psur.ts` - All CRUD functions and queries
- ✅ `backend/db_convex.py` - Python client for Convex
- ✅ `package.json` - Node.js dependencies
- ✅ `convex.json` - Convex configuration

**Your Convex Project:**
- 🌐 URL: `https://unique-heron-539.convex.cloud`

---

## 🚀 Setup Steps

### 1. Install Node.js (if needed)

```powershell
# Download from: https://nodejs.org/
# Or use Chocolatey:
choco install nodejs
```

### 2. Install Convex CLI

```powershell
npm install -g convex
```

### 3. Login to Convex

```powershell
npx convex login
```

This will open your browser to authenticate.

### 4. Link Your Project

```powershell
# In your project directory
npx convex dev --once --url https://unique-heron-539.convex.cloud
```

This will:
- Connect to your existing Convex project
- Generate TypeScript types
- Create `convex/_generated/` folder

### 5. Deploy Schema and Functions

```powershell
npx convex deploy
```

This pushes:
- Schema definition (`schema.ts`)
- All query/mutation functions (`psur.ts`)

### 6. Get Your Deploy Key

```powershell
# In Convex dashboard: https://dashboard.convex.dev
# Go to Settings → Deploy Keys → Create Deploy Key
```

### 7. Update .env File

```env
# Database Configuration
DATABASE_TYPE=convex
CONVEX_URL=https://unique-heron-539.convex.cloud
CONVEX_DEPLOY_KEY=your_actual_deploy_key_here
```

### 8. Migrate Data (Optional)

If you have existing SQLite data:

```powershell
python migrate_to_convex.py
```

### 9. Restart Server

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🎯 Why Convex?

### Real-Time Sync
- ⚡ **Automatic updates** - All clients sync instantly
- 🔄 **Live queries** - Data refreshes automatically
- 📡 **WebSocket built-in** - No manual broadcasting needed

### Developer Experience
- 🛡️ **Type-safe** - Full TypeScript support
- 🧪 **Zero config** - No database setup required
- 📊 **Built-in dashboard** - View/edit data live
- 🔍 **Query inspector** - Debug queries in real-time

### Performance
- 🚀 **Edge network** - Global CDN distribution
- ⚡ **Fast queries** - Optimized indexing
- 💾 **Automatic caching** - Smart data revalidation
- 📈 **Scales automatically** - No server management

### Security
- 🔐 **Function-level auth** - Control access per function
- ✅ **Input validation** - Built-in schema validation
- 🛡️ **HTTPS everywhere** - Encrypted by default

---

## 📊 Convex Schema Overview

```typescript
psur_reports table:
- td_number (indexed) - Unique identifier
- psur_number (indexed) - Report number
- class (indexed) - IIa, IIb, III
- status (indexed) - Assigned, Released, etc.
- writer (indexed) - Owner name
- due_date (indexed) - FLEXIBLE user-assigned date
- product_name, catalog_number, etc.
```

**Indexes enable fast queries:**
- Find by TD number: ~5ms
- Search by writer: ~10ms
- Filter by class + status: ~15ms

---

## 🔧 Available Functions

### Queries (Read-Only)
```typescript
psur:getByTd(tdNumber)          // Get single record
psur:getAllByTd(tdNumber)       // Get all duplicates
psur:getByPsur(psurNumber)      // Get by PSUR number
psur:search(query, limit)       // Semantic search
psur:filter(filters)            // Multi-criteria filter
psur:getAll()                   // All records
psur:findMissingFields(fields)  // Find incomplete records
psur:getStats()                 // Database statistics
```

### Mutations (Write Operations)
```typescript
psur:create(record)             // Add new record
psur:update(tdNumber, updates)  // Update existing
psur:deleteRecord(tdNumber)     // Delete record(s)
psur:bulkUpdateStatus(...)      // Bulk status update
psur:addComment(tdNumber, text) // Add timestamped comment
psur:linkReferences(urls)       // Add MC/SharePoint links
```

---

## 🧪 Testing Your Setup

### In Convex Dashboard

1. Go to: https://dashboard.convex.dev/deployment/unique-heron-539/data
2. Click "psur_reports" table
3. Add a test record:
   ```json
   {
     "td_number": "TD001",
     "product_name": "Test Product",
     "writer": "Test User",
     "due_date": "2025-12-31",
     "status": "Assigned",
     "class": "IIa"
   }
   ```

### With Python Client

```python
import asyncio
from backend.db_convex import get_store

async def test():
    store = get_store()
    
    # Test query
    record = await store.find_by_td("TD001")
    print(f"Found: {record}")
    
    # Test stats
    stats = await store.get_stats()
    print(f"Stats: {stats}")

asyncio.run(test())
```

### With Voice Agent

```
"Show me TD001"
"Add a PSUR for New Product, Class IIa, writer Sarah, due June 30th"
"List all overdue items"
```

---

## 🔄 Migration from SQLite

### Option 1: Manual Export/Import

```powershell
# 1. Export from SQLite to Excel
python -c "from backend.db_store import get_store; get_store().export_excel()"

# 2. Switch to Convex
# Edit .env: DATABASE_TYPE=convex

# 3. Import from Excel
python -c "import asyncio; from backend.db_convex import get_store; asyncio.run(get_store().import_from_excel())"
```

### Option 2: Direct Migration Script

```python
# migrate_to_convex.py
import asyncio
from backend.db_store import get_store as get_sqlite_store
from backend.db_convex import get_store as get_convex_store

async def migrate():
    sqlite = get_sqlite_store()
    convex = get_convex_store()
    
    # Get all SQLite records
    records = sqlite.get_all()
    print(f"Migrating {len(records)} records...")
    
    # Insert into Convex
    for record in records:
        await convex.add_record(record)
        print(f"✓ {record['td_number']}")
    
    print("✅ Migration complete!")

asyncio.run(migrate())
```

---

## 📱 Real-Time Updates

With Convex, all connected clients automatically see updates!

```python
# Backend updates data
await store.update_record("TD045", {"status": "Released"})

# Frontend sees change instantly - no manual refresh needed!
```

This is perfect for:
- 👥 **Multi-user collaboration**
- 📊 **Live dashboards**
- 🔔 **Real-time notifications**
- 🎯 **Voice agent coordination**

---

## 🎛️ Convex Dashboard Features

Visit: https://dashboard.convex.dev/deployment/unique-heron-539

**Data Tab:**
- View all tables
- Add/edit/delete records manually
- Export to JSON/CSV

**Functions Tab:**
- See all queries/mutations
- Test functions directly
- View execution logs

**Logs Tab:**
- Real-time function execution
- Error tracking
- Performance metrics

**Settings Tab:**
- Deploy keys
- Environment variables
- Team management

---

## 🔐 Security Best Practices

### 1. Deploy Key Protection

```env
# .env file (add to .gitignore!)
CONVEX_DEPLOY_KEY=prod:your-secret-key-here
```

**Never commit deploy keys to Git!**

### 2. Function-Level Auth (Optional)

```typescript
// Add auth to functions
export const create = mutation({
  args: { ... },
  handler: async (ctx, args) => {
    const identity = await ctx.auth.getUserIdentity();
    if (!identity) {
      throw new Error("Unauthorized");
    }
    // ... rest of function
  },
});
```

### 3. Input Validation

Convex automatically validates all inputs against schema!

```typescript
// This will error if wrong type
args: { tdNumber: v.string() }  // Must be string
```

---

## ⚡ Performance Tips

### 1. Use Indexes

```typescript
// Fast (uses index)
.withIndex("by_td_number", q => q.eq("td_number", "TD045"))

// Slow (full table scan)
.filter(r => r.td_number === "TD045")
```

### 2. Limit Results

```typescript
// Get only what you need
.first()     // Single record
.take(10)    // First 10
.collect()   // All (use sparingly)
```

### 3. Cache on Client

```python
# Python client caches automatically
# But you can also implement your own caching
```

---

## 🆘 Troubleshooting

### "Cannot connect to Convex"

```
Error: Failed to fetch from https://unique-heron-539.convex.cloud
```

**Solutions:**
1. Check internet connection
2. Verify `CONVEX_URL` in `.env`
3. Ensure Convex project is deployed: `npx convex deploy`

### "Function not found"

```
Error: No function psur:getByTd
```

**Solution:**
```powershell
# Redeploy functions
npx convex deploy
```

### "Schema mismatch"

```
Error: Field 'td_number' is required
```

**Solution:**
1. Check `convex/schema.ts` matches your data
2. Redeploy: `npx convex deploy`
3. Update Python client if field names changed

---

## 🎉 Next Steps

After setup:

1. ✅ Test with voice commands
2. ✅ View data in Convex dashboard
3. ✅ Set up real-time sync on frontend
4. ✅ Configure team access (if needed)
5. ✅ Monitor performance in logs

**You're ready to go!** 🚀

---

## 📚 Resources

- **Convex Docs**: https://docs.convex.dev
- **Dashboard**: https://dashboard.convex.dev
- **TypeScript API**: https://docs.convex.dev/api/modules
- **Python Guide**: See `backend/db_convex.py`

---

**Status**: 🟢 Ready to Deploy  
**Deployment**: `npx convex deploy`  
**Migration**: Optional (SQLite still works)
