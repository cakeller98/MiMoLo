import net from "node:net";
import { setTimeout as delay } from "node:timers/promises";

const socketPath = process.env.MIMOLO_IPC_PATH || "";

if (!socketPath) {
  console.error("MIMOLO_IPC_PATH is required (AF_UNIX socket path)");
  process.exit(1);
}

const client = net.createConnection({ path: socketPath }, () => {
  console.log("connected", socketPath);
});

client.setEncoding("utf8");

let buffer = "";
client.on("data", (chunk) => {
  buffer += chunk;
  let idx = buffer.indexOf("\n");
  while (idx !== -1) {
    const line = buffer.slice(0, idx).trim();
    buffer = buffer.slice(idx + 1);
    if (line.length > 0) {
      console.log("recv", line);
    }
    idx = buffer.indexOf("\n");
  }
});

client.on("error", (err) => {
  console.error("ipc error", err.message);
});

client.on("end", () => {
  console.log("ipc closed");
});

async function main(): Promise<void> {
  // Example: request registered plugins (placeholder contract)
  const msg = { cmd: "get_registered_plugins" };
  client.write(JSON.stringify(msg) + "\n");

  // Keep alive briefly so we can read responses.
  await delay(2000);
  client.end();
}

void main();
