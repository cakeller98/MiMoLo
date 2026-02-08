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

declare module "node:fs/promises" {
  export interface Stats {
    size: number;
  }

  export function readFile(
    path: string,
    encoding: "utf8"
  ): Promise<string>;
  export function stat(path: string): Promise<Stats>;
}

declare module "module" {
  interface RequireFn {
    (id: string): unknown;
  }

  export function createRequire(filename: string): RequireFn;
}
