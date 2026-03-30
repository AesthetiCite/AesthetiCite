import express, { type Request, Response, NextFunction } from "express";
import { registerRoutes } from "./routes";
import { serveStatic } from "./static";
import { createServer } from "http";
import { spawn, ChildProcess } from "child_process";
import { existsSync } from "fs";
import path from "path";

let pythonProcess: ChildProcess | null = null;
let pythonReady = false;
let pythonExited = false;

async function waitForPythonHealth(maxWaitMs = 600000): Promise<boolean> {
  const start = Date.now();
  const interval = 3000;
  let lastLog = 0;
  while (Date.now() - start < maxWaitMs) {
    // If the Python process has already exited with a failure, stop waiting immediately.
    if (pythonExited) {
      console.error("[startup] Python process exited — aborting health wait");
      return false;
    }
    try {
      const resp = await fetch("http://localhost:8000/health", { signal: AbortSignal.timeout(4000) });
      if (resp.ok) {
        return true;
      }
    } catch {}
    const elapsed = Math.round((Date.now() - start) / 1000);
    if (elapsed - lastLog >= 30) {
      console.log(`[startup] Waiting for Python API... ${elapsed}s elapsed`);
      lastLog = elapsed;
    }
    await new Promise((r) => setTimeout(r, interval));
  }
  return false;
}

/**
 * Resolve the Python binary to use.
 *
 * Priority:
 *   1. $UV_PROJECT_ENVIRONMENT/bin/python3  — direct binary from uv-managed env (fastest,
 *      works even when `uv` CLI is not in PATH at runtime)
 *   2. $UV_PATH or `uv`                     — use `uv run` which auto-activates the env
 *   3. python3                               — bare system Python (last resort)
 */
function resolvePythonCmd(): { bin: string; prefix: string[] } {
  const uvEnv = process.env.UV_PROJECT_ENVIRONMENT;
  if (uvEnv) {
    const directPy = `${uvEnv}/bin/python3`;
    if (existsSync(directPy)) {
      console.log(`[startup] Using direct Python binary: ${directPy}`);
      return { bin: directPy, prefix: ["-m"] };
    }
  }
  const uvBin = process.env.UV_PATH || "uv";
  console.log(`[startup] Using uv run: ${uvBin}`);
  return { bin: uvBin, prefix: ["run"] };
}

function spawnPython(args: string[]): ReturnType<typeof spawn> {
  const { bin, prefix } = resolvePythonCmd();
  const spawnArgs = [...prefix, ...args];
  console.log(`[startup] Spawning: ${bin} ${spawnArgs.join(" ")}`);
  return spawn(bin, spawnArgs, {
    cwd: process.cwd(),
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });
}

function attachPythonListeners(proc: ChildProcess) {
  proc.stdout?.on("data", (data) => {
    const output = data.toString().trim();
    if (output) console.log(`[python] ${output}`);
  });
  proc.stderr?.on("data", (data) => {
    const output = data.toString().trim();
    if (output) console.log(`[python] ${output}`);
  });
  proc.on("error", (err) => {
    console.error(`[python] Process error: ${err.message}`);
    pythonExited = true;
  });
  proc.on("exit", (code, signal) => {
    if (code !== 0 && code !== null) {
      console.error(`[python] Exited with code ${code} (signal: ${signal})`);
      pythonReady = false;
      pythonExited = true;
    }
  });
}

function startPythonAPIBackground() {
  // In production, start.sh launches Python independently before Node.js.
  // Node only needs to wait for the health check — no subprocess management needed.
  if (process.env.PYTHON_MANAGED_EXTERNALLY === "1") {
    console.log("Python managed externally (start.sh) — waiting for health check...");
    waitForPythonHealth().then(async (healthy) => {
      if (healthy) {
        pythonReady = true;
        console.log("Python API healthy (external)");
        await runDrizzleMigrations();
      } else {
        console.error("Python API failed to become healthy within timeout");
      }
    });
    return;
  }

  console.log("Starting Python FastAPI backend on port 8000...");
  pythonExited = false;

  pythonProcess = spawnPython(["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]);
  attachPythonListeners(pythonProcess);

  waitForPythonHealth().then(async (healthy) => {
    if (healthy) {
      pythonReady = true;
      console.log("Python API started successfully (health check passed)");
      await runDrizzleMigrations();
    } else {
      console.error("Python API failed to become healthy within timeout");
    }
  });
}

async function runDrizzleMigrations() {
  try {
    const { db } = await import("./db");
    const { migrate } = await import("drizzle-orm/node-postgres/migrator");
    const migrationsFolder = path.join(process.cwd(), "drizzle");
    await migrate(db, { migrationsFolder });
    console.log("[migrations] Drizzle migrations applied successfully");
  } catch (err: any) {
    console.error("[migrations] Migration error (non-fatal):", err?.message ?? err);
  }
}

process.on("exit", () => {
  if (pythonProcess) pythonProcess.kill();
});

process.on("SIGINT", () => {
  if (pythonProcess) pythonProcess.kill();
  process.exit();
});

process.on("SIGTERM", () => {
  if (pythonProcess) pythonProcess.kill();
  process.exit();
});

const app = express();
const httpServer = createServer(app);

declare module "http" {
  interface IncomingMessage {
    rawBody: unknown;
  }
}

app.use(
  express.json({
    verify: (req, _res, buf) => {
      req.rawBody = buf;
    },
  }),
);

app.use(express.urlencoded({ extended: false }));

export function log(message: string, source = "express") {
  const formattedTime = new Date().toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });
  console.log(`${formattedTime} [${source}] ${message}`);
}

app.use((req, res, next) => {
  const start = Date.now();
  const path = req.path;
  let capturedJsonResponse: Record<string, any> | undefined = undefined;

  const originalResJson = res.json;
  res.json = function (bodyJson, ...args) {
    capturedJsonResponse = bodyJson;
    return originalResJson.apply(res, [bodyJson, ...args]);
  };

  res.on("finish", () => {
    const duration = Date.now() - start;
    if (path.startsWith("/api")) {
      let logLine = `${req.method} ${path} ${res.statusCode} in ${duration}ms`;
      if (capturedJsonResponse) {
        logLine += ` :: ${JSON.stringify(capturedJsonResponse)}`;
      }
      log(logLine);
    }
  });

  next();
});

app.get("/health", (_req, res) => {
  res.json({ status: "ok", python_ready: pythonReady });
});

(async () => {
  await registerRoutes(httpServer, app);

  app.use((err: any, _req: Request, res: Response, next: NextFunction) => {
    const status = err.status || err.statusCode || 500;
    const message = err.message || "Internal Server Error";
    console.error("Internal Server Error:", err);
    if (res.headersSent) return next(err);
    return res.status(status).json({ message });
  });

  if (process.env.NODE_ENV === "production") {
    serveStatic(app);
  } else {
    const { setupVite } = await import("./vite");
    await setupVite(httpServer, app);
  }

  const port = parseInt(process.env.PORT || "5000", 10);
  httpServer.listen(
    { port, host: "0.0.0.0", reusePort: true },
    () => {
      log(`serving on port ${port}`);
      startPythonAPIBackground();
    },
  );
})();
