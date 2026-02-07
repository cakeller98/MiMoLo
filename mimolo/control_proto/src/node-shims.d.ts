declare module "node:net" {
  type ErrorWithMessage = { message: string };

  export interface Socket {
    setEncoding(encoding: string): void;
    on(event: "data", listener: (chunk: string) => void): this;
    on(event: "error", listener: (err: ErrorWithMessage) => void): this;
    on(event: "end", listener: () => void): this;
    write(data: string): void;
    end(): void;
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
