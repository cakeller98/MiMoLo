import type { AgentTemplateSnapshot } from "./types.js";

export class TemplateCache {
  private cache:
    | { fetchedAtMs: number; templates: Record<string, AgentTemplateSnapshot> }
    | null = null;
  private refreshInFlight: Promise<Record<string, AgentTemplateSnapshot>> | null = null;
  private readonly getTtlMs: () => number;

  constructor(getTtlMs: () => number) {
    this.getTtlMs = getTtlMs;
  }

  async getTemplates(
    forceRefresh: boolean,
    refreshFn: () => Promise<Record<string, AgentTemplateSnapshot>>,
  ): Promise<Record<string, AgentTemplateSnapshot>> {
    const now = Date.now();
    if (
      !forceRefresh &&
      this.cache &&
      now - this.cache.fetchedAtMs < this.getTtlMs()
    ) {
      return this.cache.templates;
    }
    if (this.refreshInFlight) {
      return this.refreshInFlight;
    }
    this.refreshInFlight = (async () => {
      const templates = await refreshFn();
      this.cache = {
        templates,
        fetchedAtMs: Date.now(),
      };
      return templates;
    })();
    try {
      return await this.refreshInFlight;
    } finally {
      this.refreshInFlight = null;
    }
  }
}
