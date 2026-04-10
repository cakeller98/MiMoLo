import { readFile, readdir, rename, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import type {
  IpcResponsePayload,
  IpcTrafficClass,
  PendingIpcRequest,
} from "./types.js";

interface SlowpokeIpcTimingSnapshot {
  backoffEscalateAfter: number;
  backoffExtendedMs: number;
  backoffInitialMs: number;
  requestTimeoutMs: number;
}

interface SlowpokeIpcClientDependencies {
  getTimingSnapshot: () => SlowpokeIpcTimingSnapshot;
  maxPendingRequests?: number;
  parseResponse: (rawLine: string) => IpcResponsePayload;
  publishLine: (line: string) => void;
  publishTraffic: (
    direction: "tx" | "rx",
    kind: IpcTrafficClass,
    label?: string,
  ) => void;
  slowpokeRoot: string;
}

export class SlowpokeIpcClient {
  private readonly deps: SlowpokeIpcClientDependencies;
  private readonly maxPendingRequests: number;
  private readonly controlToOpsDir: string;
  private readonly opsToControlDir: string;
  private inFlightRequest: PendingIpcRequest | null = null;
  private queueDrainRunning = false;
  private requestCounter = 0;
  private connectFailureCount = 0;
  private nextConnectAttemptAt = 0;
  private readonly pendingRequestQueue: PendingIpcRequest[] = [];

  public constructor(deps: SlowpokeIpcClientDependencies) {
    this.deps = deps;
    this.maxPendingRequests = deps.maxPendingRequests ?? 256;
    this.controlToOpsDir = path.join(deps.slowpokeRoot, "control_to_ops");
    this.opsToControlDir = path.join(deps.slowpokeRoot, "ops_to_control");
  }

  public async sendCommand(
    cmd: string,
    extraPayload?: Record<string, unknown>,
    trafficLabel?: string,
    trafficClass: IpcTrafficClass = "interactive",
  ): Promise<IpcResponsePayload> {
    const providedRequestId =
      extraPayload &&
      typeof extraPayload.request_id === "string" &&
      extraPayload.request_id.trim().length > 0
        ? extraPayload.request_id.trim()
        : "";
    const requestId =
      providedRequestId || `ctrl-${Date.now()}-${++this.requestCounter}`;
    const requestPayload: Record<string, unknown> = {
      cmd,
      ...(extraPayload || {}),
      request_id: requestId,
    };

    const responsePromise = new Promise<IpcResponsePayload>((resolve, reject) => {
      if (this.pendingRequestQueue.length >= this.maxPendingRequests) {
        reject(new Error("ipc_queue_overloaded"));
        return;
      }
      this.pendingRequestQueue.push({
        id: requestId,
        payload: requestPayload,
        resolve,
        reject,
        timeoutHandle: null,
        trafficClass,
        trafficLabel,
      });
    });

    void this.drainQueue();
    return responsePromise;
  }

  public resetBackoff(): void {
    this.connectFailureCount = 0;
    this.nextConnectAttemptAt = 0;
  }

  public stop(reason: string): void {
    if (this.inFlightRequest) {
      const inFlight = this.inFlightRequest;
      this.inFlightRequest = null;
      inFlight.reject(new Error(reason));
    }

    while (this.pendingRequestQueue.length > 0) {
      const pending = this.pendingRequestQueue.shift();
      if (!pending) {
        continue;
      }
      pending.reject(new Error(reason));
    }
  }

  private recordConnectFailure(): void {
    this.connectFailureCount += 1;
    const timing = this.deps.getTimingSnapshot();
    const backoffMs =
      this.connectFailureCount >= timing.backoffEscalateAfter
        ? timing.backoffExtendedMs
        : timing.backoffInitialMs;
    this.nextConnectAttemptAt = Date.now() + Math.max(1, backoffMs);
  }

  private async ensureReady(): Promise<void> {
    const now = Date.now();
    if (now < this.nextConnectAttemptAt) {
      throw new Error("ipc_connect_backoff");
    }
    if (!this.deps.slowpokeRoot) {
      throw new Error("ipc_slowpoke_root_missing");
    }

    try {
      await readdir(this.controlToOpsDir);
      await readdir(this.opsToControlDir);
      this.resetBackoff();
    } catch {
      this.recordConnectFailure();
      throw new Error("ipc_slowpoke_not_ready");
    }
  }

  private async writeRequest(payload: Record<string, unknown>): Promise<void> {
    const baseName = `${Date.now()}_${++this.requestCounter}_${Math.random()
      .toString(36)
      .slice(2, 10)}`;
    const tempPath = path.join(this.controlToOpsDir, `${baseName}.tmp`);
    const finalPath = path.join(this.controlToOpsDir, `${baseName}.json`);
    await writeFile(tempPath, JSON.stringify(payload), { flag: "wx" });
    await rename(tempPath, finalPath);
  }

  private async readResponse(): Promise<string | null> {
    const responseFiles = (await readdir(this.opsToControlDir))
      .filter((name) => name.endsWith(".json"))
      .sort();
    if (responseFiles.length === 0) {
      return null;
    }

    const responsePath = path.join(this.opsToControlDir, responseFiles[0]);
    try {
      return await readFile(responsePath, "utf8");
    } finally {
      await unlink(responsePath).catch(() => undefined);
    }
  }

  private async waitForResponse(
    request: PendingIpcRequest,
    timeoutMs: number,
  ): Promise<IpcResponsePayload> {
    const deadline = Date.now() + Math.max(1, timeoutMs);
    while (Date.now() < deadline) {
      const raw = await this.readResponse();
      if (!raw) {
        await delay(100);
        continue;
      }

      try {
        const parsed = this.deps.parseResponse(raw.trim());
        if (parsed.request_id && parsed.request_id !== request.id) {
          this.deps.publishLine(
            `[ipc] request_id mismatch: expected=${request.id} got=${parsed.request_id}`,
          );
          continue;
        }
        return parsed;
      } catch (err) {
        const detail = err instanceof Error ? err.message : "invalid_response";
        this.deps.publishLine(`[ipc] invalid slowpoke response: ${detail}`);
      }
    }

    throw new Error("timeout");
  }

  private rejectPendingQueue(reason: string): void {
    while (this.pendingRequestQueue.length > 0) {
      const pending = this.pendingRequestQueue.shift();
      if (!pending) {
        continue;
      }
      pending.reject(new Error(reason));
    }
  }

  private async drainQueue(): Promise<void> {
    if (this.queueDrainRunning) {
      return;
    }
    this.queueDrainRunning = true;

    try {
      while (!this.inFlightRequest && this.pendingRequestQueue.length > 0) {
        try {
          await this.ensureReady();
        } catch (err) {
          const detail =
            err instanceof Error ? err.message : "ipc_connect_failed";
          this.rejectPendingQueue(detail);
          return;
        }

        const nextRequest = this.pendingRequestQueue.shift();
        if (!nextRequest) {
          return;
        }

        const timing = this.deps.getTimingSnapshot();
        this.inFlightRequest = nextRequest;
        this.deps.publishTraffic(
          "tx",
          nextRequest.trafficClass,
          nextRequest.trafficLabel,
        );

        try {
          await this.writeRequest(nextRequest.payload);
          const response = await this.waitForResponse(
            nextRequest,
            timing.requestTimeoutMs,
          );
          this.deps.publishTraffic(
            "rx",
            nextRequest.trafficClass,
            nextRequest.trafficLabel,
          );
          nextRequest.resolve(response);
        } catch (err) {
          const detail =
            err instanceof Error ? err.message : "ipc_slowpoke_failed";
          nextRequest.reject(new Error(detail));
        } finally {
          this.inFlightRequest = null;
        }
      }
    } finally {
      this.queueDrainRunning = false;
    }
  }
}
