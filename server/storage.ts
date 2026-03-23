import { randomUUID } from "crypto";

export interface SearchHistoryItem {
  id: string;
  query: string;
  timestamp: Date;
}

export interface IStorage {
  addSearchHistory(query: string): Promise<SearchHistoryItem>;
  getSearchHistory(): Promise<SearchHistoryItem[]>;
}

export class MemStorage implements IStorage {
  private searchHistory: Map<string, SearchHistoryItem>;

  constructor() {
    this.searchHistory = new Map();
  }

  async addSearchHistory(query: string): Promise<SearchHistoryItem> {
    const id = randomUUID();
    const item: SearchHistoryItem = {
      id,
      query,
      timestamp: new Date(),
    };
    this.searchHistory.set(id, item);
    return item;
  }

  async getSearchHistory(): Promise<SearchHistoryItem[]> {
    return Array.from(this.searchHistory.values())
      .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())
      .slice(0, 50);
  }
}

export const storage = new MemStorage();
