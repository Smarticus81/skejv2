# PSUR-OPS Agent Tool Reference

## Complete Tool Inventory (39 tools)

### 🔍 **Query & Retrieval Tools**

#### `normalize_id`
Normalize TD/PSUR mentions into canonical format.
- **Input**: `query` (string) - e.g., "td 45", "psur-012"
- **Output**: `{td_number, psur_number}` - e.g., "TD045", "PSUR012"

#### `get_report`
Fetch a single record by TD Number.
- **Input**: `row_id` (TD Number)
- **Output**: Single record or empty result

#### `get_report_by_psur`
Fetch a single record by PSUR Number.
- **Input**: `psur_id` (PSUR Number)
- **Output**: Single record or empty result

#### `get_all_duplicates`
Get ALL records sharing the same TD Number (for multi-product TDs).
- **Input**: `td_number`
- **Output**: Array of all matching records

#### `get_field_value`
Extract a specific field value from a record.
- **Input**: `row_id`, `field_name`
- **Output**: `{field_name, field_value}`

#### `find_reports`
Semantic/fuzzy search across all text fields.
- **Input**: `query`, `limit` (default 50)
- **Output**: Array of matching records

#### `list_reports`
Paginated list with optional filter object.
- **Input**: `offset`, `limit`, `filters`
- **Output**: Paginated results with total count

#### `list_due_items`
Items due within N days with optional filters.
- **Input**: `within_days`, `classification`, `writer`, `status`
- **Output**: Filtered array sorted by due date

#### `list_overdue_items`
Items past their due date.
- **Input**: `classification`, `writer`
- **Output**: Overdue items sorted by due date

#### `list_by_writer`
All items assigned to a specific writer.
- **Input**: `writer`, `status` (optional)
- **Output**: Filtered array

#### `list_by_class_type`
Filter by device class or report type.
- **Input**: `classification`, `type`, `status`
- **Output**: Filtered array

#### `list_by_status`
All reports with a specific status.
- **Input**: `status`
- **Output**: Filtered array

#### `list_by_product`
Find all reports for a product name.
- **Input**: `product_name`
- **Output**: Matching records

#### `list_missing_fields`
Find records missing specific required fields.
- **Input**: `fields` (array of field names)
- **Output**: Records with `missing_fields` annotation

#### `get_stats`
Database-wide statistics.
- **Input**: None
- **Output**: `{total_records, by_status, by_class, by_writer, overdue, due_soon, duplicate_td_numbers}`

---

### ✏️ **Single-Record Update Tools**

#### `update_schedule_row`
Generic multi-field update by TD Number.
- **Input**: `row_id`, `updates` (object)
- **Output**: `{ok: true}` or error

#### `update_field`
Update a single field value.
- **Input**: `row_id`, `field_name`, `field_value`
- **Output**: `{ok: true}` or error

#### `update_status`
Update only the status field.
- **Input**: `row_id`, `status`
- **Output**: `{ok: true}` or error

#### `update_writer`
Reassign writer/owner with optional email.
- **Input**: `row_id`, `writer`, `email` (optional)
- **Output**: `{ok: true}` or error

#### `update_due_date`
Update only the due date field.
- **Input**: `row_id`, `due_date`
- **Output**: `{ok: true}` or error

#### `update_periods`
Update start and/or end period.
- **Input**: `row_id`, `start_period` (optional), `end_period` (optional)
- **Output**: `{ok: true}` or error

#### `update_canada_flags`
Update Canada-related fields.
- **Input**: `row_id`, `canada_needed` (optional), `canada_status` (optional)
- **Output**: `{ok: true}` or error

#### `clear_field`
Blank out a specific field.
- **Input**: `row_id`, `field_name`
- **Output**: `{ok: true}` or error

#### `add_comment`
Append timestamped comment to Comments field.
- **Input**: `row_id`, `comment`
- **Output**: `{ok: true}` or error

#### `link_references`
Attach MasterControl and/or SharePoint URLs.
- **Input**: `row_id`, `mastercontrol_url` (optional), `sharepoint_url` (optional)
- **Output**: `{ok: true}` or error

---

### 📦 **Bulk Update Tools**

#### `bulk_update_status`
Update status for all records matching a filter.
- **Input**: `filter` (object), `new_status`
- **Output**: `{ok: true, updated_count}`

#### `bulk_update_writer`
Reassign writer for all records matching a filter.
- **Input**: `filter` (object), `new_writer`, `new_email` (optional)
- **Output**: `{ok: true, updated_count}`

#### `bulk_update_field`
Update any field for all records matching a filter.
- **Input**: `filter` (object), `field_name`, `field_value`
- **Output**: `{ok: true, updated_count}`

---

### ➕ **Create & Delete Tools**

#### `add_psur_item`
Create a new PSUR report record.
- **Input**: All field names (optional) - auto-generates TD if omitted
- **Output**: `{ok: true, td_number}`

#### `clone_report`
Duplicate an existing report with optional modifications.
- **Input**: `source_td`, `new_td` (optional), `modifications` (object)
- **Output**: `{ok: true, td_number}`

#### `delete_report`
Delete a report by TD Number (removes ALL records with that TD).
- **Input**: `row_id`
- **Output**: `{ok: true}` or error

---

### 🧮 **Validation & Computation Tools**

#### `compute_expected_due_date`
Calculate expected due date from end period and frequency.
- **Input**: `end_period`, `frequency`, `buffer_days` (default 0)
- **Output**: `{expected_due_date}` (ISO date string)

#### `validate_row`
Compliance checks for a single record.
- **Input**: `row_id` OR `psur_id`
- **Output**: `{issues}` (array of validation warnings)

#### `compare_due_dates`
Compare stored vs. computed due date.
- **Input**: `row_id` OR `psur_id`
- **Output**: `{stored, expected}`

---

### 📤 **Export Tools**

#### `export_calendar`
Generate ICS calendar file.
- **Input**: `filter` (optional), `within_days` (optional), `filename` (default "psur_schedule.ics")
- **Output**: `{file_url}`

#### `export_csv`
Export to CSV.
- **Input**: `filter` (optional), `filename` (default "psur_export.csv")
- **Output**: `{file_url}`

#### `export_excel`
Export to Excel workbook.
- **Input**: `filter` (optional), `filename` (default "psur_export.xlsx")
- **Output**: `{file_url}`

---

### 🔄 **Data Management Tools**

#### `reload_from_excel`
Reimport all data from source Excel file.
- **Input**: None
- **Output**: `{ok: true, loaded_count}`

---

## Field Names Reference

**Canonical field names** (use in `update_*` tools):
- `td_number` - TD Number (identifier)
- `psur_number` - PSUR Number
- `class` - Device Class (I, IIa, IIb, III)
- `type` - Report Type
- `product_name` - Product Name
- `catalog_number` - Catalog Number
- `writer` - Writer/Owner
- `email` - Writer Email
- `start_period` - Start Period (date)
- `end_period` - End Period (date)
- `frequency` - Frequency (Annual, Biennial, 5-Year)
- `due_date` - Due Date (date)
- `status` - Status (Assigned, Released, Routing, etc.)
- `canada_needed` - Canada Summary Report Needed
- `canada_status` - Canada Summary Report Status
- `comments` - Comments

---

## Usage Patterns

### Example: Update a single field
```json
{
  "name": "update_field",
  "args": {
    "row_id": "TD045",
    "field_name": "status",
    "field_value": "Released"
  }
}
```

### Example: Bulk reassign writer
```json
{
  "name": "bulk_update_writer",
  "args": {
    "filter": {"classification": "III", "status": "Assigned"},
    "new_writer": "Jane Doe",
    "new_email": "jane.doe@example.com"
  }
}
```

### Example: Clone a report
```json
{
  "name": "clone_report",
  "args": {
    "source_td": "TD045",
    "new_td": "TD156",
    "modifications": {
      "product_name": "New Product Variant",
      "writer": "John Smith"
    }
  }
}
```

### Example: Get all products under one TD
```json
{
  "name": "get_all_duplicates",
  "args": {
    "td_number": "TD045"
  }
}
```

---

## Tool Selection Guide

| User Intent | Recommended Tool |
|-------------|------------------|
| "Open TD045" | `get_report` |
| "Find Hyadase" | `find_reports` |
| "What's due in 60 days?" | `list_due_items` |
| "Show overdue for Jeff" | `list_overdue_items` |
| "Mark TD045 as Released" | `update_status` |
| "Change due date to March 15" | `update_due_date` |
| "Reassign all Class III to Sarah" | `bulk_update_writer` |
| "Add a new PSUR" | `add_psur_item` |
| "Copy TD045 as TD156" | `clone_report` |
| "Delete TD099" | `delete_report` |
| "Export next 90 days to calendar" | `export_calendar` |
| "Is TD045 compliant?" | `validate_row` |
| "What's the expected due date?" | `compute_expected_due_date` |
| "Show database stats" | `get_stats` |

---

## Notes

- All update tools broadcast changes via WebSocket to connected clients
- TD Numbers are NOT unique - use `get_all_duplicates` for multi-product records
- Date fields accept ISO format (YYYY-MM-DD) or common US formats (MM/DD/YYYY)
- Filter objects support: `writer`, `classification`, `status`, `within_days`, `overdue_only`
- All tools return structured JSON responses with consistent error handling
