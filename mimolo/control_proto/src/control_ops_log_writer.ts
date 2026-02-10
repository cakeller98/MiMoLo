import { writeFile } from "node:fs/promises";

export class OpsLogWriter {
  private readonly path: string;
  private writeQueue: Promise<void> = Promise.resolve();

  constructor(path: string) {
    this.path = path;
  }

  append(rawChunk: unknown): void {
    if (!this.path) {
      return;
    }
    const chunk =
      typeof rawChunk === "string"
        ? rawChunk
        : (rawChunk && typeof rawChunk === "object" && "toString" in rawChunk
          ? String((rawChunk as { toString: () => string }).toString())
          : "");
    if (chunk.length === 0) {
      return;
    }
    this.writeQueue = this.writeQueue
      .then(() => writeFile(this.path, chunk, { flag: "a" }))
      .catch(() => {
        // Keep the write chain alive on transient write failures.
      });
  }
}
