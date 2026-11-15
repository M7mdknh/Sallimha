// Copies the approved brand files (tokens, licensed fonts, SVG assets) from
// /brand into public/brand so the console self-hosts them. Never edit the copies.
import { cpSync, mkdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, "../../../brand");
const target = resolve(here, "../public/brand");
rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
for (const item of ["tokens.css", "fonts", "assets"]) {
  cpSync(resolve(source, item), resolve(target, item), { recursive: true });
}
console.log(`brand synced to ${target}`);
