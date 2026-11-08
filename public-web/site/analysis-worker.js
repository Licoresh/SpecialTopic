import {csvRow, MAX_BUFFERED_EXPORT_BYTES, readCsv} from './csv.js';
import {isMissing, normalize} from './analysis-rules.js';

const REQUIRED_TEXT = ['job_description', 'required_skills', 'preferred_skills', 'qualifications'];
const MAX_ROWS = 100_000;
const headersKey = text => text.normalize('NFKC').toLowerCase().replace(/[^a-z0-9]/g, '');
const clip = (text, limit = 240) => text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
let referencePromise;

function loadReference() {
  return referencePromise ??= fetch(new URL('./reference.json', import.meta.url), {credentials: 'omit'})
    .then(response => {
      if (!response.ok) throw new Error('The built-in reference could not be loaded. Refresh the page and try again.');
      return response.json();
    });
}

function suggestMapping(fields, columns, rawHeaders) {
  const mapping = Object.fromEntries(Object.keys(fields).map(field => [field, '']));
  const used = new Set();
  const rawKeys = rawHeaders.map(headersKey);
  for (const exact of [true, false]) {
    for (const [field, aliases] of Object.entries(fields)) {
      if (mapping[field]) continue;
      const names = new Set((exact ? [field] : aliases).map(headersKey));
      const choices = columns.filter((name, index) => !used.has(name) && names.has(rawKeys[index]));
      if (choices.length === 1) {
        mapping[field] = choices[0];
        used.add(choices[0]);
      }
    }
  }
  return mapping;
}

async function inspect(file) {
  const reference = await loadReference();
  let columns, mapping;
  const preview = [];
  await readCsv(file, {
    onHeader(labels, raw) {
      columns = labels;
      mapping = suggestMapping(reference.columns, labels, raw);
    },
    onRow(row) {
      if (row.some(value => value.trim())) preview.push(Object.fromEntries(columns.map((name, index) => [name, clip(row[index] ?? '', 140)])));
      return preview.length < 5;
    },
  });
  if (!preview.length) throw new Error('The file has headers but no job-ad records.');
  return {type: 'inspection', filename: file.name, size: file.size, columns, mapping, preview};
}

function mapColumns(mapping, fields, columns) {
  const used = new Set();
  const indexes = Object.entries(fields).map(([field]) => {
    const header = mapping?.[field];
    if (!header) return [field, -1];
    const index = columns.indexOf(header);
    if (index < 0 || used.has(index)) throw new Error('Each confirmed field needs its own column from this CSV.');
    used.add(index);
    return [field, index];
  });
  if (!mapping?.job_title || !REQUIRED_TEXT.some(field => mapping[field])) {
    throw new Error('Map Job title and at least one description, skills, or qualifications column.');
  }
  return row => Object.fromEntries(indexes.map(([field, index]) => [field, (row[index] ?? '').trim()]));
}

async function visit(file, mapping, fields, onAd, onChunk) {
  const summary = {rows: 0, ads: 0, duplicates: 0, blank: 0};
  let mapped;
  await readCsv(file, {
    onHeader(columns) { mapped = mapColumns(mapping, fields, columns); },
    onRow(row, sourceRow) {
      if (++summary.rows > MAX_ROWS) throw new Error('The CSV has more than 100,000 records. Split it into smaller files.');
      const job = mapped(row);
      if (['job_title', ...REQUIRED_TEXT].every(field => isMissing(job[field]))) {
        summary.blank++;
        return;
      }
      summary.ads++;
      onAd(job, sourceRow);
    },
    onChunk,
  });
  return summary;
}

const sendProgress = (percent, message) => self.postMessage({type: 'progress', percent, message});

async function exportCleaned(file, mapping, handle) {
  if (!handle && file.size > MAX_BUFFERED_EXPORT_BYTES) throw new Error('Saving a large cleaned CSV needs Chrome or Edge with direct file saving. Chart tables can still be downloaded.');
  const reference = await loadReference();
  const fields = Object.keys(reference.columns);
  const identity = new Set(['job_id', 'source_id', 'url', 'posting_date', 'collected_at_utc']);
  const sink = handle ? await handle.createWritable() : null;
  const buffers = [];
  let chunk = '\uFEFF' + csvRow(['source_row', ...fields]);
  async function flush() {
    if (!chunk) return;
    if (sink) await sink.write(chunk);
    else buffers.push(chunk);
    chunk = '';
  }
  try {
    const summary = await visit(file, mapping, reference.columns, (job, sourceRow) => {
      chunk += csvRow([sourceRow, ...fields.map(field => identity.has(field) ? job[field] : normalize(job[field]))]);
    }, async (bytes, total) => {
      await flush();
      sendProgress(Math.round(100 * bytes / total), 'Writing the cleaned CSV…');
    });
    await flush();
    if (sink) await sink.close();
    return {type: 'exported', filename: 'cleaned_job_ads.csv', rows: summary.ads,
      ...(sink ? {} : {blob: new Blob(buffers, {type: 'text/csv;charset=utf-8'})})};
  } catch (error) {
    if (sink) await sink.abort().catch(() => {});
    throw error;
  }
}

let active = false;
self.addEventListener('message', async ({data}) => {
  if (active) return;
  active = true;
  try {
    const {type, file, mapping, handle} = data;
    if (type === 'inspect') self.postMessage(await inspect(file));
    else if (type === 'export') self.postMessage(await exportCleaned(file, mapping, handle));
    else throw new Error('Unknown analysis operation.');
  } catch (error) {
    if (error instanceof RangeError) self.postMessage({type: 'error', message: 'This device ran out of working space. Split the CSV into smaller files and try again.'});
    else self.postMessage({type: 'error', message: error?.message || 'The file could not be processed.'});
  } finally {
    active = false;
  }
});
