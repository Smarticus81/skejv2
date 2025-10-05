// Convex Functions for PSUR Schedule Operations
import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// ========== QUERIES ==========

export const getByTd = query({
  args: { tdNumber: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("psur_reports")
      .withIndex("by_td_number", (q) => q.eq("td_number", args.tdNumber))
      .first();
  },
});

export const getAllByTd = query({
  args: { tdNumber: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("psur_reports")
      .withIndex("by_td_number", (q) => q.eq("td_number", args.tdNumber))
      .collect();
  },
});

export const getByPsur = query({
  args: { psurNumber: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("psur_reports")
      .withIndex("by_psur_number", (q) => q.eq("psur_number", args.psurNumber))
      .first();
  },
});

export const search = query({
  args: { query: v.string(), limit: v.optional(v.number()) },
  handler: async (ctx, args) => {
    const limit = args.limit || 50;
    const queryLower = args.query.toLowerCase();
    
    // Get all records and filter in memory (Convex will optimize this)
    const all = await ctx.db.query("psur_reports").collect();
    
    const matches = all.filter((record) => {
      const searchFields = [
        record.td_number,
        record.psur_number,
        record.product_name,
        record.catalog_number,
        record.writer,
        record.class,
        record.status,
      ].map(f => (f || "").toLowerCase());
      
      return searchFields.some(field => field.includes(queryLower));
    });
    
    return matches.slice(0, limit);
  },
});

export const filter = query({
  args: {
    writer: v.optional(v.string()),
    classification: v.optional(v.string()),
    status: v.optional(v.string()),
    dueBefore: v.optional(v.string()),
    overdue: v.optional(v.boolean()),
  },
  handler: async (ctx, args) => {
    let results = await ctx.db.query("psur_reports").collect();
    
    // Apply filters
    if (args.writer) {
      const writerLower = args.writer.toLowerCase();
      results = results.filter(r => (r.writer || "").toLowerCase().includes(writerLower));
    }
    
    if (args.classification) {
      const classLower = args.classification.toLowerCase();
      results = results.filter(r => (r.class || "").toLowerCase() === classLower);
    }
    
    if (args.status) {
      const statusLower = args.status.toLowerCase();
      results = results.filter(r => (r.status || "").toLowerCase() === statusLower);
    }
    
    if (args.dueBefore) {
      results = results.filter(r => r.due_date && r.due_date <= args.dueBefore!);
    }
    
    if (args.overdue) {
      const today = new Date().toISOString().split('T')[0];
      results = results.filter(r => r.due_date && r.due_date < today);
    }
    
    // Sort by due date
    return results.sort((a, b) => {
      if (!a.due_date) return 1;
      if (!b.due_date) return -1;
      return a.due_date.localeCompare(b.due_date);
    });
  },
});

export const getAll = query({
  handler: async (ctx) => {
    return await ctx.db.query("psur_reports").collect();
  },
});

export const findMissingFields = query({
  args: { fields: v.array(v.string()) },
  handler: async (ctx, args) => {
    const all = await ctx.db.query("psur_reports").collect();
    
    return all.filter((record) => {
      return args.fields.some((field) => {
        const value = (record as any)[field];
        return !value || value === "";
      });
    });
  },
});

export const getStats = query({
  handler: async (ctx) => {
    const all = await ctx.db.query("psur_reports").collect();
    const today = new Date().toISOString().split('T')[0];
    
    // Count by status
    const byStatus: Record<string, number> = {};
    const byClass: Record<string, number> = {};
    const byWriter: Record<string, number> = {};
    const tdCounts: Record<string, number> = {};
    
    let overdueCount = 0;
    
    for (const record of all) {
      // Status
      if (record.status) {
        byStatus[record.status] = (byStatus[record.status] || 0) + 1;
      }
      
      // Class
      if (record.class) {
        byClass[record.class] = (byClass[record.class] || 0) + 1;
      }
      
      // Writer
      if (record.writer) {
        byWriter[record.writer] = (byWriter[record.writer] || 0) + 1;
      }
      
      // Overdue
      if (record.due_date && record.due_date < today) {
        overdueCount++;
      }
      
      // Duplicate TDs
      if (record.td_number) {
        tdCounts[record.td_number] = (tdCounts[record.td_number] || 0) + 1;
      }
    }
    
    const duplicateTds = Object.entries(tdCounts)
      .filter(([_, count]) => count > 1)
      .map(([td, _]) => td);
    
    return {
      total_records: all.length,
      by_status: byStatus,
      by_class: byClass,
      by_writer: byWriter,
      overdue_count: overdueCount,
      duplicate_td_numbers: duplicateTds,
    };
  },
});

// ========== MUTATIONS ==========

export const create = mutation({
  args: {
    td_number: v.optional(v.string()),
    psur_number: v.optional(v.string()),
    class: v.optional(v.string()),
    type: v.optional(v.string()),
    product_name: v.optional(v.string()),
    catalog_number: v.optional(v.string()),
    writer: v.optional(v.string()),
    email: v.optional(v.string()),
    start_period: v.optional(v.string()),
    end_period: v.optional(v.string()),
    frequency: v.optional(v.string()),
    due_date: v.optional(v.string()),
    status: v.optional(v.string()),
    canada_needed: v.optional(v.string()),
    canada_status: v.optional(v.string()),
    comments: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    // Auto-generate TD number if not provided
    let tdNumber = args.td_number;
    
    if (!tdNumber) {
      const all = await ctx.db.query("psur_reports").collect();
      const tdNumbers = all
        .map(r => r.td_number)
        .filter(td => /^TD\d+$/.test(td))
        .map(td => parseInt(td.substring(2)));
      
      const maxTd = tdNumbers.length > 0 ? Math.max(...tdNumbers) : 0;
      tdNumber = `TD${String(maxTd + 1).padStart(3, '0')}`;
    }
    
    const now = new Date().toISOString();
    
    const id = await ctx.db.insert("psur_reports", {
      ...args,
      td_number: tdNumber,
      created_at: now,
      updated_at: now,
      version: 1,
    });
    
    return { td_number: tdNumber, id };
  },
});

export const update = mutation({
  args: {
    tdNumber: v.string(),
    updates: v.any(),
  },
  handler: async (ctx, args) => {
    const record = await ctx.db
      .query("psur_reports")
      .withIndex("by_td_number", (q) => q.eq("td_number", args.tdNumber))
      .first();
    
    if (!record) {
      return false;
    }
    
    const now = new Date().toISOString();
    
    await ctx.db.patch(record._id, {
      ...args.updates,
      updated_at: now,
      version: (record.version || 1) + 1,
    });
    
    return true;
  },
});

export const deleteRecord = mutation({
  args: { tdNumber: v.string() },
  handler: async (ctx, args) => {
    const records = await ctx.db
      .query("psur_reports")
      .withIndex("by_td_number", (q) => q.eq("td_number", args.tdNumber))
      .collect();
    
    for (const record of records) {
      await ctx.db.delete(record._id);
    }
    
    return records.length > 0;
  },
});

export const bulkUpdateStatus = mutation({
  args: {
    filter: v.any(),
    newStatus: v.string(),
  },
  handler: async (ctx, args) => {
    // For now, implement basic filtering
    let records = await ctx.db.query("psur_reports").collect();
    
    // Apply filters (simplified)
    if (args.filter.writer) {
      const writerLower = args.filter.writer.toLowerCase();
      records = records.filter(r => (r.writer || "").toLowerCase().includes(writerLower));
    }
    
    if (args.filter.classification) {
      const classLower = args.filter.classification.toLowerCase();
      records = records.filter(r => (r.class || "").toLowerCase() === classLower);
    }
    
    const now = new Date().toISOString();
    let count = 0;
    
    for (const record of records) {
      await ctx.db.patch(record._id, {
        status: args.newStatus,
        updated_at: now,
        version: (record.version || 1) + 1,
      });
      count++;
    }
    
    return count;
  },
});

export const addComment = mutation({
  args: {
    tdNumber: v.string(),
    comment: v.string(),
  },
  handler: async (ctx, args) => {
    const record = await ctx.db
      .query("psur_reports")
      .withIndex("by_td_number", (q) => q.eq("td_number", args.tdNumber))
      .first();
    
    if (!record) {
      return false;
    }
    
    const existingComments = record.comments || "";
    const newComments = existingComments 
      ? `${existingComments}\n${args.comment}`
      : args.comment;
    
    const now = new Date().toISOString();
    
    await ctx.db.patch(record._id, {
      comments: newComments,
      updated_at: now,
      version: (record.version || 1) + 1,
    });
    
    return true;
  },
});

export const linkReferences = mutation({
  args: {
    tdNumber: v.string(),
    mastercontrolUrl: v.optional(v.string()),
    sharepointUrl: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const record = await ctx.db
      .query("psur_reports")
      .withIndex("by_td_number", (q) => q.eq("td_number", args.tdNumber))
      .first();
    
    if (!record) {
      return false;
    }
    
    const now = new Date().toISOString();
    const updates: any = { updated_at: now, version: (record.version || 1) + 1 };
    
    if (args.mastercontrolUrl) {
      updates.mastercontrol_url = args.mastercontrolUrl;
    }
    if (args.sharepointUrl) {
      updates.sharepoint_url = args.sharepointUrl;
    }
    
    await ctx.db.patch(record._id, updates);
    
    return true;
  },
});
