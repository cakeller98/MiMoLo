declare module "node:net" {
  type ErrorWithMessage = { message: string };

  export interface Socket {
    setEncoding(encoding: string): void;
    on(event: "connect", listener: () => void): this;
    on(event: "data", listener: (chunk: string) => void): this;
    on(event: "error", listener: (err: ErrorWithMessage) => void): this;
    on(event: "close", listener: () => void): this;
    on(event: "end", listener: () => void): this;
    write(data: string): void;
    end(): void;
    destroy(): void;
    removeAllListeners(): this;
  }

  export interface ConnectionOptions {
    path: string;
  }

  interface NetModule {
    createConnection(
      options: ConnectionOptions,
      connectionListener?: () => void
    ): Socket;
  }

  const net: NetModule;
  export default net;
}

declare module "node:timers/promises" {
  export function setTimeout(ms: number): Promise<void>;
}

declare module "node:child_process" {
  export interface ChildProcessStream {
    on(event: "data", listener: (chunk: unknown) => void): this;
  }

  export interface SpawnedChildProcess {
    kill(signal?: string): boolean;
    on(event: "error", listener: (error: { message?: string }) => void): this;
    on(
      event: "exit",
      listener: (code: number | null, signal: string | null) => void
    ): this;
    pid?: number;
    stderr: ChildProcessStream | null;
    stdout: ChildProcessStream | null;
  }

  export interface SpawnOptions {
    cwd?: string;
    env?: Record<string, string | undefined>;
    stdio?: Array<"ignore" | "pipe">;
  }

  export function spawn(
    command: string,
    args?: string[],
    options?: SpawnOptions
  ): SpawnedChildProcess;
}

declare module "node:fs/promises" {
  export interface Stats {
    size: number;
  }

  export interface WriteFileOptions {
    flag?: string;
  }

  export function readFile(
    path: string,
    encoding: "utf8"
  ): Promise<string>;
  export function stat(path: string): Promise<Stats>;
  export function mkdir(
    path: string,
    options?: { recursive?: boolean }
  ): Promise<void>;
  export function writeFile(
    path: string,
    data: string,
    options?: WriteFileOptions
  ): Promise<void>;
}

declare module "node:path" {
  interface PathModule {
    dirname(path: string): string;
  }

  const path: PathModule;
  export default path;
}

declare module "module" {
  interface RequireFn {
    (id: string): unknown;
  }

  export function createRequire(filename: string): RequireFn;
}
