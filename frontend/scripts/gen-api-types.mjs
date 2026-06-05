#!/usr/bin/env node
/**
 * Genera los tipos TypeScript del contrato OpenAPI a partir del esquema
 * versionado en el repo (`src/api/openapi.json`).
 *
 * El backend usa drf-yasg, que emite Swagger 2.0. openapi-typescript solo
 * acepta OpenAPI 3.x, así que el pipeline es:
 *
 *   src/api/openapi.json (Swagger 2.0, fuente de verdad versionada)
 *     → swagger2openapi  → OpenAPI 3.0 (temporal)
 *     → openapi-typescript → src/api/schema.d.ts (tipos versionados)
 *
 * Modos:
 *   node scripts/gen-api-types.mjs          → regenera src/api/schema.d.ts
 *   node scripts/gen-api-types.mjs --check  → falla si el resultado difiere
 *                                             de lo versionado (drift)
 *
 * El esquema NO se regenera aquí desde el backend (eso requiere Django+BD).
 * Para refrescarlo, ver README §"Sincronizar el contrato con el backend".
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const SCHEMA = join(ROOT, 'src', 'api', 'openapi.json');
const OUT = join(ROOT, 'src', 'api', 'schema.d.ts');

const check = process.argv.includes('--check');

if (!existsSync(SCHEMA)) {
  console.error(`No se encuentra el esquema versionado: ${SCHEMA}`);
  console.error('Regenéralo desde el backend (ver README) antes de continuar.');
  process.exit(1);
}

// Resolvemos los binarios JS directamente y los ejecutamos con node, en lugar
// de npx.cmd, para ser cross-plataforma sin problemas de shell en Windows.
const node = process.execPath;
const swagger2openapiBin = join(ROOT, 'node_modules', 'swagger2openapi', 'swagger2openapi.js');
const openapiTsBin = join(ROOT, 'node_modules', 'openapi-typescript', 'bin', 'cli.js');

const tmp = mkdtempSync(join(tmpdir(), 'omni-openapi-'));
const openapi3 = join(tmp, 'openapi3.json');

// Swagger 2.0 → OpenAPI 3.0
execFileSync(node, [swagger2openapiBin, SCHEMA, '-o', openapi3], {
  stdio: ['ignore', 'ignore', 'inherit'],
});

// OpenAPI 3.0 → tipos TS (a stdout para poder comparar sin tocar el repo)
const generated = execFileSync(node, [openapiTsBin, openapi3], {
  encoding: 'utf8',
  maxBuffer: 64 * 1024 * 1024,
});

const banner =
  '/**\n' +
  ' * ARCHIVO GENERADO — NO EDITAR A MANO.\n' +
  ' * Fuente: src/api/openapi.json (contrato del backend).\n' +
  ' * Regenerar: npm run gen:api-types\n' +
  ' * Verificar drift: npm run check:api-drift\n' +
  ' */\n';
const content = banner + generated;

if (check) {
  const current = existsSync(OUT) ? readFileSync(OUT, 'utf8') : '';
  // Normaliza saltos de línea para evitar falsos positivos por CRLF/LF.
  const norm = (s) => s.replace(/\r\n/g, '\n');
  if (norm(current) !== norm(content)) {
    console.error('❌ Drift de contrato API: src/api/schema.d.ts está desactualizado.');
    console.error('   El esquema versionado (src/api/openapi.json) genera tipos distintos.');
    console.error('   Corre `npm run gen:api-types` y commitea el resultado.');
    process.exit(1);
  }
  console.log('✅ Sin drift: src/api/schema.d.ts coincide con el esquema versionado.');
} else {
  writeFileSync(OUT, content);
  console.log(`✅ Tipos generados en ${OUT}`);
}
