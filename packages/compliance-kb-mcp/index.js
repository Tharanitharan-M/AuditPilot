#!/usr/bin/env node
import { spawn } from "node:child_process";

const python = process.env.PYTHON || "python";
const args = ["-m", "compliance_kb_mcp.server"];

const child = spawn(python, args, {
  stdio: "inherit",
  env: process.env,
});

child.on("exit", (code) => {
  process.exit(code ?? 0);
});
