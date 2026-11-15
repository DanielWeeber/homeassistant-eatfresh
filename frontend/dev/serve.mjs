// Tiny static server for the panel dev page. Serves the integration folder
// and maps /eatfresh/... to dev/index.html, like the Home Assistant panel URL.
// Usage: npm run serve   (then open http://127.0.0.1:5180/eatfresh)
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const port = Number(process.env.PORT ?? 5180);
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml" };

createServer(async (req, res) => {
  let path = decodeURIComponent(new URL(req.url ?? "/", "http://x").pathname);
  if (path === "/" || path === "/eatfresh" || path.startsWith("/eatfresh/")) path = "/frontend/dev/index.html";
  const file = normalize(join(root, path));
  if (!file.startsWith(root) || file.includes("node_modules")) {
    res.writeHead(403).end();
    return;
  }
  try {
    const body = await readFile(file);
    res.writeHead(200, { "content-type": types[extname(file)] ?? "application/octet-stream", "cache-control": "no-store" });
    res.end(body);
  } catch {
    res.writeHead(404).end("not found");
  }
}).listen(port, "127.0.0.1", () => console.log(`EatFresh dev page: http://127.0.0.1:${port}/eatfresh`));
