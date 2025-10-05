// Convex Schema Definition for PSUR Schedule
import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  psur_reports: defineTable({
    // Core identifiers
    td_number: v.string(),
    psur_number: v.optional(v.string()),
    
    // Classification
    class: v.optional(v.string()),
    type: v.optional(v.string()),
    
    // Product information
    product_name: v.optional(v.string()),
    catalog_number: v.optional(v.string()),
    
    // Ownership
    writer: v.optional(v.string()),
    email: v.optional(v.string()),
    
    // Timeline
    start_period: v.optional(v.string()), // ISO date
    end_period: v.optional(v.string()),   // ISO date
    frequency: v.optional(v.string()),
    due_date: v.optional(v.string()),     // ISO date - FLEXIBLE, user-assigned
    
    // Status tracking
    status: v.optional(v.string()),
    
    // Canada-specific
    canada_needed: v.optional(v.string()),
    canada_status: v.optional(v.string()),
    
    // Notes and references
    comments: v.optional(v.string()),
    mastercontrol_url: v.optional(v.string()),
    sharepoint_url: v.optional(v.string()),
    
    // Metadata
    created_at: v.optional(v.string()),
    updated_at: v.optional(v.string()),
    version: v.optional(v.number()),
  })
    // Indexes for fast queries
    .index("by_td_number", ["td_number"])
    .index("by_psur_number", ["psur_number"])
    .index("by_writer", ["writer"])
    .index("by_status", ["status"])
    .index("by_class", ["class"])
    .index("by_due_date", ["due_date"]),
});
