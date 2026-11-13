// Makes dist/specstream-adobe-express.zip, the file Adobe's "Upload package" step takes: the files of
// src/ at the root of the zip (manifest.json first), relative paths only, no hidden files. No dependency:
// the zip is written here, stored without compression (the add-on is a few kilobytes).
import { readdirSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { crc32 } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));

export function zip(files) {
  const parts = [];
  const central = [];
  let offset = 0;
  for (const { name, data } of files) {
    const n = Buffer.from(name, 'utf8');
    const crc = crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4); // version needed
    local.writeUInt16LE(0x0800, 6); // names are UTF-8
    local.writeUInt16LE(0, 8); // stored
    local.writeUInt16LE(0, 10); // time
    local.writeUInt16LE(0x21, 12); // date 1980-01-01, so the same source gives the same zip
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(n.length, 26);
    const head = Buffer.alloc(46);
    head.writeUInt32LE(0x02014b50, 0);
    head.writeUInt16LE(20, 4);
    head.writeUInt16LE(20, 6);
    head.writeUInt16LE(0x0800, 8);
    head.writeUInt16LE(0, 10);
    head.writeUInt16LE(0, 12);
    head.writeUInt16LE(0x21, 14);
    head.writeUInt32LE(crc, 16);
    head.writeUInt32LE(data.length, 20);
    head.writeUInt32LE(data.length, 24);
    head.writeUInt16LE(n.length, 28);
    head.writeUInt32LE(offset, 42);
    parts.push(local, n, data);
    central.push(head, n);
    offset += local.length + n.length + data.length;
  }
  const dir = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(files.length, 8);
  end.writeUInt16LE(files.length, 10);
  end.writeUInt32LE(dir.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...parts, dir, end]);
}

export function packageFiles(src = join(here, 'src')) {
  const names = readdirSync(src).filter((f) => !f.startsWith('.')).sort();
  names.sort((a, b) => (a === 'manifest.json' ? -1 : b === 'manifest.json' ? 1 : 0));
  return names.map((name) => {
    let data = readFileSync(join(src, name));
    if (name === 'manifest.json') {
      // testId and name are for local development; the marketplace takes the name from the listing.
      const m = JSON.parse(data.toString('utf8'));
      delete m.testId;
      delete m.name;
      data = Buffer.from(`${JSON.stringify(m, null, 2)}\n`, 'utf8');
    }
    return { name, data };
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const out = join(here, 'dist');
  mkdirSync(out, { recursive: true });
  const files = packageFiles();
  writeFileSync(join(out, 'specstream-adobe-express.zip'), zip(files));
  console.log(`dist/specstream-adobe-express.zip: ${files.map((f) => f.name).join(', ')}`);
}
