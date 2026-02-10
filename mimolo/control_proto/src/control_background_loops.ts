type PollIntervals = {
  statusMs: number;
  logMs: number;
  instanceMs: number;
};

type BackgroundLoopDeps = {
  loadInitialSnapshot: () => Promise<void>;
  refreshStatus: () => Promise<void>;
  refreshInstances: () => Promise<void>;
  pumpLog: () => Promise<void>;
  deriveIntervals: () => PollIntervals;
  stopPersistentIpc: () => void;
};

export class BackgroundLoopController {
  private statusTimer: ReturnType<typeof setInterval> | null = null;
  private logTimer: ReturnType<typeof setInterval> | null = null;
  private instanceTimer: ReturnType<typeof setInterval> | null = null;
  private readonly deps: BackgroundLoopDeps;

  constructor(deps: BackgroundLoopDeps) {
    this.deps = deps;
  }

  restart(): void {
    this.clearTimers();

    const { statusMs, logMs, instanceMs } = this.deps.deriveIntervals();

    this.statusTimer = setInterval(() => {
      void this.deps.refreshStatus();
    }, statusMs);

    this.logTimer = setInterval(() => {
      void this.deps.pumpLog();
    }, logMs);

    this.instanceTimer = setInterval(() => {
      void this.deps.refreshInstances();
    }, instanceMs);
  }

  start(): void {
    void this.deps.loadInitialSnapshot();
    void this.deps.pumpLog();
    void this.deps.refreshInstances();
    this.restart();
  }

  stop(): void {
    this.clearTimers();
    this.deps.stopPersistentIpc();
  }

  private clearTimers(): void {
    if (this.statusTimer) {
      clearInterval(this.statusTimer);
      this.statusTimer = null;
    }
    if (this.logTimer) {
      clearInterval(this.logTimer);
      this.logTimer = null;
    }
    if (this.instanceTimer) {
      clearInterval(this.instanceTimer);
      this.instanceTimer = null;
    }
  }
}
