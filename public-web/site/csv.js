const CHUNK_BYTES = 1024 * 1024;
const MAX_ROW = 8 * CHUNK_BYTES;
const MAX_COLUMNS = 512;
export const MAX_CSV_BYTES = 500 * CHUNK_BYTES;
export const MAX_BUFFERED_EXPORT_BYTES = 32 * CHUNK_BYTES;

function separator(text) {
  const counts = new Map([[',', 0], ['\t', 0], [';', 0]]);
  let quoted = false;
  for (const character of text) {
    if (character === '"') quoted = !quoted;
    else if (!quoted && /[\r\n]/.test(character)) break;
    else if (!quoted && counts.has(character)) counts.set(character, counts.get(character) + 1);
  }
  const [[delimiter, count]] = [...counts].sort((a, b) => b[1] - a[1]);
  if (!count) throw new Error('Expected a CSV with a comma, tab, or semicolon separated header.');
  return delimiter;
}

function headerLabels(row) {
  const seen = new Set();
  return row.map((cell, index) => {
    const base = cell.trim() || `Column ${index + 1}`;
    let label = base;
    for (let occurrence = 2; seen.has(label); occurrence++) label = `${base} [${occurrence}]`;
    seen.add(label);
    return label;
  });
}

function parser(delimiter, onHeader, onRow) {
  let row = [], field = '', state = 'start', skipLF = false, size = 0;
  let header, recordNumber = 0;
  function finishField() {
    row.push(field);
    if (row.length > MAX_COLUMNS) throw new Error(`CSV record ${recordNumber + 1} exceeds ${MAX_COLUMNS} columns.`);
    field = '';
    state = 'start';
  }
  function finishRow() {
    finishField();
    recordNumber++;
    let keepReading;
    if (!header) {
      header = headerLabels(row);
      if (!row.some(value => value.trim())) throw new Error('The first CSV record must contain column headers.');
      onHeader(header, row.map(cell => cell.trim()));
    } else {
      if (row.length > header.length) throw new Error(`CSV record ${recordNumber} has more columns than the header.`);
      keepReading = onRow(row, recordNumber);
    }
    row = [];
    size = 0;
    return keepReading;
  }
  return (chunk, done = false) => {
    for (let index = 0; index < chunk.length; index++) {
      const character = chunk[index];
      if (skipLF) {
        skipLF = false;
        if (character === '\n') continue;
      }
      if (++size > MAX_ROW) throw new Error(`CSV record ${recordNumber + 1} is too large. The limit is 8 million characters per record.`);
      if (state === 'quoted') {
        if (character === '"') state = 'quoteEnd';
        else field += character;
      } else if (state === 'quoteEnd' && character === '"') {
        field += '"';
        state = 'quoted';
      } else if (character === delimiter) {
        finishField();
      } else if (character === '\n' || character === '\r') {
        skipLF = character === '\r';
        if (finishRow() === false) return false;
      } else if (state === 'quoteEnd') {
        throw new Error(`Unexpected text after a closing quote in CSV record ${recordNumber + 1}.`);
      } else if (character === '"' && state === 'start') {
        state = 'quoted';
      } else {
        if (character === '"') throw new Error(`Unescaped quote in CSV record ${recordNumber + 1}.`);
        field += character;
        state = 'text';
      }
    }
    if (done && state === 'quoted') throw new Error(`CSV record ${recordNumber + 1} has an unclosed quoted field.`);
    if (done && size) return finishRow();
    return true;
  };
}

export async function readCsv(file, {onHeader, onRow, onChunk = () => {}}) {
  if (!file || !/\.(?:csv|tsv)$/i.test(file.name)) throw new Error('Choose a .csv or .tsv file. Export Excel workbooks as CSV UTF-8 first.');
  if (!file.size) throw new Error('The selected file is empty.');
  if (file.size > MAX_CSV_BYTES) throw new Error('The selected file exceeds the 500 MB limit. Split it before analysis.');
  let decoder, feed;
  for (let start = 0; start < file.size; start += CHUNK_BYTES) {
    const end = Math.min(start + CHUNK_BYTES, file.size);
    const bytes = new Uint8Array(await file.slice(start, end).arrayBuffer());
    if (!decoder) {
      const encoding = bytes[0] === 0xff && bytes[1] === 0xfe ? 'utf-16le'
        : bytes[0] === 0xfe && bytes[1] === 0xff ? 'utf-16be' : 'utf-8';
      decoder = new TextDecoder(encoding, {fatal: true});
    }
    let text;
    try {
      text = decoder.decode(bytes, {stream: end < file.size});
    } catch {
      throw new Error('The file has an unsupported text encoding or invalid bytes. Export it as CSV UTF-8 and try again.');
    }
    if (text.includes('\0')) throw new Error('The file contains NUL bytes. Export it as CSV UTF-8 and try again.');
    if (!feed) feed = parser(separator(text), onHeader, onRow);
    if (feed(text, end === file.size) === false) break;
    await onChunk(end, file.size);
  }
}

export function csvRow(values) {
  return values.map(value => {
    let cell = String(value ?? '');
    if (/^(?:\s*[=+\-@]|[\t\r\n])/u.test(cell.normalize('NFKC'))) cell = "'" + cell;
    return '"' + cell.replaceAll('"', '""') + '"';
  }).join(',') + '\r\n';
}
