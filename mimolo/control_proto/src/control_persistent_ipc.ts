import net from "node:net";
import type {
  IpcResponsePayload,
  IpcTrafficClass,
  PendingIpcRequest,
} from "./types.js";

interface PersistentIpcTimingSnapshot {
  backoffEscalateAfter: number;
  backoffExtendedMs: number;
  backoffInitialMs: number;
  requestTimeoutMs: number;
}

interface PersistentIpcClientDependencies {
  getTimingSnapshot: () => PersistentIpcTimingSnapshot;
  ipcPath: string;
  maxPendingRequests?: number;
  parseResponse: (rawLine: string) => IpcResponsePayload;
  publishLine: (line: string) => void;
  publishTraffic: (
    direction: "tx" | "rx",
    kind: IpcTrafficClass,
    label?: string,
  ) => void;
}

type IpcSocket = ReturnType<typeof net.createConnection>;

export class PersistentIpcClient {
  private readonly deps: PersistentIpcClientDependencies;
  private readonly maxPendingRequests: number;
  private socket: IpcSocket | null = null;
  private socketState: "disconnected" | "connecting" | "connected" =
    "disconnected";
  private socketBuffer = "";
  private connectPromise: Promise<void> | null = null;
  private connectResolve: (() => void) | null = null;
  private connectReject: ((error: Error) => void) | null = null;
  private inFlightRequest: PendingIpcRequest | null = null;
  private queueDrainRunning = false;
  private requestCounter = 0;
  private connectFailureCount = 0;
  private nextConnectAttemptAt = 0;
  private readonly pendingRequestQueue: PendingIpcRequest[] = [];

  public constructor(deps: PersistentIpcClientDependencies) {
    this.deps = deps;
    this.maxPendingRequests = deps.maxPendingRequests ?? 256;
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
    const requestId = providedRequestId || `ctrl-${Date.now()}-${++this.requestCounter}`;
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
    if (this.socket) {
      this.socket.removeAllListeners();
      this.socket.destroy();
      this.socket = null;
    }
    this.socketBuffer = "";
    this.socketState = "disconnected";
    if (this.connectReject) {
      this.connectReject(new Error(reason));
    }
    this.connectPromise = null;
    this.connectResolve = null;
    this.connectReject = null;

    if (this.inFlightRequest) {
      const inFlight = this.inFlightRequest;
      this.inFlightRequest = null;
      this.clearRequestTimeout(inFlight);
      inFlight.reject(new Error(reason));
    }

    while (this.pendingRequestQueue.length > 0) {
      const pending = this.pendingRequestQueue.shift();
      if (!pending) {
        continue;
      }
      this.clearRequestTimeout(pending);
      pending.reject(new Error(reason));
    }
  }

  private clearRequestTimeout(request: PendingIpcRequest): void {
    if (!request.timeoutHandle) {
      return;
    }
    clearTimeout(request.timeoutHandle);
    request.timeoutHandle = null;
  }

  private settleInFlightWithError(reason: string): void {
    if (!this.inFlightRequest) {
      return;
    }
    const request = this.inFlightRequest;
    this.inFlightRequest = null;
    this.clearRequestTimeout(request);
    request.reject(new Error(reason));
  }

  private rejectPendingQueue(reason: string): void {
    while (this.pendingRequestQueue.length > 0) {
      const pending = this.pendingRequestQueue.shift();
      if (!pending) {
        continue;
      }
      this.clearRequestTimeout(pending);
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

  private handleSocketDisconnect(reason: string): void {
    if (this.socket) {
      this.socket.removeAllListeners();
      this.socket.destroy();
      this.socket = null;
    }

    this.socketBuffer = "";
    this.socketState = "disconnected";
    if (this.connectReject) {
      this.connectReject(new Error(reason));
    }
    this.connectPromise = null;
    this.connectResolve = null;
    this.connectReject = null;
    this.recordConnectFailure();

    this.settleInFlightWithError(reason);
    this.rejectPendingQueue(reason);
  }

  private resolveInFlightResponse(response: IpcResponsePayload): void {
    if (!this.inFlightRequest) {
      this.deps.publishLine(`[ipc] unsolicited response: ${JSON.stringify(response)}`);
      return;
    }

    const request = this.inFlightRequest;
    const responseRequestId = response.request_id;
    if (responseRequestId && responseRequestId !== request.id) {
      this.deps.publishLine(
        `[ipc] request_id mismatch: expected=${request.id} got=${responseRequestId}`,
      );
      return;
    }

    this.inFlightRequest = null;
    this.clearRequestTimeout(request);
    this.deps.publishTraffic("rx", request.trafficClass, request.trafficLabel);
    request.resolve(response);
    void this.drainQueue();
  }

  private parseSocketBuffer(): void {
    while (true) {
      const newlineIndex = this.socketBuffer.indexOf("\n");
      if (newlineIndex < 0) {
        return;
      }
      const rawLine = this.socketBuffer.slice(0, newlineIndex).trim();
      this.socketBuffer = this.socketBuffer.slice(newlineIndex + 1);
      if (rawLine.length === 0) {
        continue;
      }
      try {
        const parsed = this.deps.parseResponse(rawLine);
        this.resolveInFlightResponse(parsed);
      } catch (err) {
        const detail = err instanceof Error ? err.message : "invalid_response";
        this.settleInFlightWithError(detail);
        void this.drainQueue();
      }
    }
  }

  private async ensureConnection(): Promise<void> {
    if (this.socketState === "connected" && this.socket) {
      return;
    }

    if (this.socketState === "connecting" && this.connectPromise) {
      return this.connectPromise;
    }

    const now = Date.now();
    if (now < this.nextConnectAttemptAt) {
      throw new Error("ipc_connect_backoff");
    }

    this.socketState = "connecting";
    this.connectPromise = new Promise<void>((resolve, reject) => {
      this.connectResolve = resolve;
      this.connectReject = reject;
    });

    const socket = net.createConnection({ path: this.deps.ipcPath });
    socket.setEncoding("utf8");
    this.socket = socket;

    socket.on("connect", () => {
      this.socketState = "connected";
      this.resetBackoff();
      const resolver = this.connectResolve;
      this.connectResolve = null;
      this.connectReject = null;
      this.connectPromise = null;
      if (resolver) {
        resolver();
      }
    });

    socket.on("data", (chunk: string) => {
      this.socketBuffer += chunk;
      this.parseSocketBuffer();
    });

    socket.on("error", (err: { message: string }) => {
      const reason = err.message || "ipc_socket_error";
      this.handleSocketDisconnect(reason);
    });

    socket.on("close", () => {
      this.handleSocketDisconnect("ipc_socket_closed");
    });

    return this.connectPromise;
  }

  private async drainQueue(): Promise<void> {
    if (this.queueDrainRunning) {
      return;
    }
    this.queueDrainRunning = true;

    try {
      while (!this.inFlightRequest && this.pendingRequestQueue.length > 0) {
        try {
          await this.ensureConnection();
        } catch (err) {
          const detail = err instanceof Error ? err.message : "ipc_connect_failed";
          this.rejectPendingQueue(detail);
          return;
        }

        const nextRequest = this.pendingRequestQueue.shift();
        if (!nextRequest || !this.socket) {
          return;
        }

        const timing = this.deps.getTimingSnapshot();
        const requestTimeoutMs = Math.max(1, timing.requestTimeoutMs);
        this.inFlightRequest = nextRequest;
        this.deps.publishTraffic(
          "tx",
          nextRequest.trafficClass,
          nextRequest.trafficLabel,
        );
        nextRequest.timeoutHandle = setTimeout(() => {
          const timeoutRequest = this.inFlightRequest;
          if (!timeoutRequest || timeoutRequest.id !== nextRequest.id) {
            return;
          }
          this.handleSocketDisconnect("timeout");
          void this.drainQueue();
        }, requestTimeoutMs);

        try {
          this.socket.write(`${JSON.stringify(nextRequest.payload)}\n`);
        } catch (err) {
          const detail = err instanceof Error ? err.message : "ipc_write_failed";
          this.handleSocketDisconnect(detail);
          nextRequest.reject(new Error(detail));
          void this.drainQueue();
        }

        return;
      }
    } finally {
      this.queueDrainRunning = false;
    }
  }
}
