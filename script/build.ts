import { build as esbuild } from "esbuild";
import { build as viteBuild } from "vite";
import { rm, readFile } from "fs/promises";
import { existsSync } from "fs";
import { execSync } from "child_process";

// server deps to bundle to reduce openat(2) syscalls
// which helps cold start times
const allowlist = [
  "@google/generative-ai",
  "axios",
  "connect-pg-simple",
  "cors",
  "date-fns",
  "drizzle-orm",
  "drizzle-zod",
  "express",
  "express-rate-limit",
  "express-session",
  "jsonwebtoken",
  "memorystore",
  "multer",
  "nanoid",
  "nodemailer",
  "openai",
  "passport",
  "passport-local",
  "pg",
  "stripe",
  "uuid",
  "ws",
  "xlsx",
  "zod",
  "zod-validation-error",
];

async function buildAll() {
  await rm("dist", { recursive: true, force: true });

  console.log("installing Python dependencies...");
  try {
    execSync("uv sync --frozen", { stdio: "inherit" });
    console.log("Python dependencies installed");
  } catch {
    try {
      execSync("python3 -c \"import uvicorn; print('Python dependencies OK')\"", { stdio: "inherit" });
    } catch {
      console.warn("Warning: could not verify Python dependencies — continuing build");
    }
  }

  console.log("pre-warming fastembed ONNX model cache...");
  try {
    // Use direct Python binary from the uv-managed env if available (avoids uv run overhead
    // and works even if UV_PROJECT_ENVIRONMENT is set to a non-standard path).
    const uvEnv = process.env.UV_PROJECT_ENVIRONMENT;
    const directPy = uvEnv ? `${uvEnv}/bin/python3` : null;
    const pyCmd = directPy && existsSync(directPy)
      ? `"${directPy}" -c`
      : `uv run python3 -c`;
    execSync(
      `${pyCmd} "from app.rag.embedder import embed_text; embed_text('warm'); print('fastembed model cached OK')"`,
      { stdio: "inherit" }
    );
  } catch {
    console.warn("Warning: fastembed model pre-warm failed — will download at runtime");
  }

  console.log("building client...");
  await viteBuild();

  console.log("building server...");
  const pkg = JSON.parse(await readFile("package.json", "utf-8"));
  const allDeps = [
    ...Object.keys(pkg.dependencies || {}),
    ...Object.keys(pkg.devDependencies || {}),
  ];
  const externals = allDeps.filter((dep) => !allowlist.includes(dep));

  await esbuild({
    entryPoints: ["server/index.ts"],
    platform: "node",
    bundle: true,
    format: "cjs",
    outfile: "dist/index.cjs",
    define: {
      "process.env.NODE_ENV": '"production"',
    },
    minify: true,
    external: externals,
    logLevel: "info",
  });
}

buildAll().catch((err) => {
  console.error(err);
  process.exit(1);
});
