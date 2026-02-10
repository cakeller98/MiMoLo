import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

type PublishLine = (line: string) => void;

export class OpsLogTailer {
  private readonly opsLogPath: string;
  private readonly publishLine: PublishLine;
  private logCursor = 0;
  private missingFileWarningPrinted = false;

  constructor(opsLogPath: string, publishLine: PublishLine) {
    this.opsLogPath = opsLogPath;
    this.publishLine = publishLine;
  }

  async initializeLogFile(): Promise<void> {
    if (!this.opsLogPath) {
      return;
    }
    try {
      await mkdir(path.dirname(this.opsLogPath), { recursive: true });
      await writeFile(this.opsLogPath, "", { flag: "a" });
    } catch (err) {
      const detail = err instanceof Error ? err.message : "ops_log_init_failed";
      this.publishLine(`[ops-log] init failed: ${detail}`);
    }
  }

  async pump(): Promise<void> {
    if (!this.opsLogPath) {
      return;
    }

    try {
      const fileStats = await stat(this.opsLogPath);
      if (fileStats.size === 0) {
        this.logCursor = 0;
        return;
      }

      const fullText = await readFile(this.opsLogPath, "utf8");
      if (fullText.length < this.logCursor) {
        this.logCursor = 0;
      }

      if (fullText.length === this.logCursor) {
        return;
      }

      const slice = fullText.slice(this.logCursor);
      this.logCursor = fullText.length;

      const lines = slice.split(/\r?\n/);
      for (const line of lines) {
        if (line.trim().length > 0) {
          this.publishLine(line);
        }
      }
      this.missingFileWarningPrinted = false;
    } catch (err) {
      if (
        err &&
        typeof err === "object" &&
        "code" in err &&
        (err as { code?: string }).code === "ENOENT"
      ) {
        if (!this.missingFileWarningPrinted) {
          this.publishLine(`[ops-log] waiting for file: ${this.opsLogPath}`);
          this.missingFileWarningPrinted = true;
        }
        return;
      }
      const detail = err instanceof Error ? err.message : "ops_log_read_failed";
      this.publishLine(`[ops-log] read failed: ${detail}`);
    }
  }
}
