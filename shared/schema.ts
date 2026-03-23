import { z } from "zod";
import { pgTable, text, timestamp, serial, varchar, bigint, customType } from "drizzle-orm/pg-core";
import { sql } from "drizzle-orm";
import { createInsertSchema } from "drizzle-zod";

const vector = customType<{ data: number[]; config: { dimensions: number } }>({
  dataType(config) {
    return `vector(${config?.dimensions ?? 384})`;
  },
});

export const searchQuerySchema = z.object({
  query: z.string().min(1, "Query is required").max(1000, "Query too long"),
});

export type SearchQuery = z.infer<typeof searchQuerySchema>;

export interface Citation {
  id: number;
  title: string;
  source: string;
  url?: string;
  year?: number;
  authors?: string;
}

export interface SearchResponse {
  answer: string;
  citations: Citation[];
  relatedQuestions: string[];
}

export interface SearchHistoryItem {
  id: string;
  query: string;
  timestamp: Date;
}

export const searchHistory = pgTable("search_history", {
  id: serial("id").primaryKey(),
  query: varchar("query", { length: 500 }).notNull(),
  answer: text("answer"),
  embedding: vector("embedding", { dimensions: 384 }),
  createdAt: timestamp("created_at", { withTimezone: true }).default(sql`now()`),
});

export const conversations = pgTable("conversations", {
  id: text("id").primaryKey(),
  createdAt: timestamp("created_at", { withTimezone: true }).default(sql`now()`),
  userId: text("user_id"),
  title: text("title"),
});

export const messages = pgTable("messages", {
  id: bigint("id", { mode: "number" }).primaryKey().notNull(),
  conversationId: text("conversation_id").notNull(),
  role: text("role").notNull(),
  content: text("content").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).default(sql`now()`),
});

export const insertSearchHistorySchema = createInsertSchema(searchHistory).omit({
  id: true,
  createdAt: true,
  embedding: true,
});
export const insertConversationSchema = createInsertSchema(conversations).omit({ createdAt: true });
export const insertMessageSchema = createInsertSchema(messages).omit({ id: true, createdAt: true });

export type InsertSearchHistory = typeof insertSearchHistorySchema._type;
export type SearchHistoryRow = typeof searchHistory.$inferSelect;
export type InsertConversation = typeof insertConversationSchema._type;
export type Conversation = typeof conversations.$inferSelect;
export type InsertMessage = typeof insertMessageSchema._type;
export type Message = typeof messages.$inferSelect;

export type InsertUser = { email: string; passwordHash: string; fullName?: string };
export type User = {
  id: string;
  email: string;
  passwordHash: string;
  isActive: boolean;
  role: string;
  createdAt: Date;
  fullName?: string | null;
  practitionerId?: string | null;
  clinicId?: string | null;
  emailVerified?: boolean | null;
  emailVerifiedAt?: Date | null;
};
