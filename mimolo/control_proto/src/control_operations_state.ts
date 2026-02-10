import type {
  OperationsControlSnapshot,
  OperationsProcessState,
} from "./types.js";

type PublishOpsStateFn = (state: OperationsControlSnapshot) => void;

export class OperationsStateStore {
  private readonly publishState: PublishOpsStateFn;
  private state: OperationsControlSnapshot;

  constructor(publishState: PublishOpsStateFn) {
    this.publishState = publishState;
    this.state = {
      state: "stopped",
      detail: "not_managed",
      managed: false,
      pid: null,
      timestamp: new Date().toISOString(),
    };
  }

  get(): OperationsControlSnapshot {
    return this.state;
  }

  set(
    state: OperationsProcessState,
    detail: string,
    managed: boolean,
    pid: number | null,
  ): void {
    if (
      this.state.state === state &&
      this.state.detail === detail &&
      this.state.managed === managed &&
      this.state.pid === pid
    ) {
      return;
    }
    this.state = {
      state,
      detail,
      managed,
      pid,
      timestamp: new Date().toISOString(),
    };
    this.publishState(this.state);
  }
}
