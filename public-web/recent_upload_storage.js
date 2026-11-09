const DATABASE = "future-of-work-streamlit-upload-cache";
const STORE = "uploads";
const SESSION_KEY = "future-of-work-streamlit-upload-session";
const MAX_AGE = 30 * 24 * 60 * 60 * 1000;
const HEARTBEAT = 6 * 60 * 60 * 1000;
let database;
let restoreStarted = false;
let lastSavedRevision;

function openDatabase() {
  database ??= new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("Browser storage is busy"));
  });
  return database;
}

async function use(mode, action) {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const request = action(tx.objectStore(STORE));
    let result;
    if (request) {
      request.onsuccess = () => { result = request.result; };
      request.onerror = () => reject(request.error);
    }
    tx.oncomplete = () => resolve(result);
    tx.onabort = () => reject(tx.error);
    tx.onerror = () => reject(tx.error);
  });
}

async function purgeExpired() {
  const db = await openDatabase();
  await new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    const request = tx.objectStore(STORE).openCursor();
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) return;
      if (cursor.value.expiresAt <= Date.now()) cursor.delete();
      cursor.continue();
    };
    tx.oncomplete = resolve;
    tx.onabort = () => reject(tx.error);
    tx.onerror = () => reject(tx.error);
  });
}

function currentSession(create = false) {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id && create) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

async function restore() {
  await purgeExpired();
  const id = currentSession();
  if (!id) return null;
  const record = await use("readonly", store => store.get(id));
  if (!record) return null;
  if (record.schema !== 1 || record.expiresAt <= Date.now()) {
    await use("readwrite", store => store.delete(id));
    return null;
  }
  record.expiresAt = Date.now() + MAX_AGE;
  await use("readwrite", store => store.put(record, id));
  return record;
}

async function renew() {
  const id = currentSession();
  if (!id) return;
  const record = await use("readonly", store => store.get(id));
  if (!record) return;
  record.expiresAt = Date.now() + MAX_AGE;
  await use("readwrite", store => store.put(record, id));
}

async function save(record) {
  const id = currentSession(true);
  await use("readwrite", store => store.put({
    schema: 1,
    fileHash: record.fileHash,
    filename: record.filename,
    content: record.content,
    mapping: record.mapping,
    expiresAt: Date.now() + MAX_AGE,
  }, id));
}

async function update(record) {
  const id = currentSession();
  if (!id) return false;
  const current = await use("readonly", store => store.get(id));
  if (!current || current.fileHash !== record.fileHash) return false;
  await use("readwrite", store => store.put({
    ...current,
    filename: record.filename,
    mapping: record.mapping,
    expiresAt: Date.now() + MAX_AGE,
  }, id));
  return true;
}

export default function (component) {
  const { data, setStateValue } = component ?? {};
  if (!data || typeof setStateValue !== "function") return;
  if (data.action === "restore" && !restoreStarted) {
    restoreStarted = true;
    restore().then(record => setStateValue("recent", record ?? null))
      .catch(() => {
        restoreStarted = false;
        setStateValue("error", "Browser storage is unavailable.");
      });
    window.setInterval(() => renew().catch(() => {}), HEARTBEAT);
  }
  if (["save", "update"].includes(data.action) && data.revision && lastSavedRevision !== data.revision) {
    lastSavedRevision = data.revision;
    const saveRecord = data.action === "save" ? save(data.record) : update(data.record);
    saveRecord.then(() => setStateValue("saved", data.revision))
      .catch(() => {
        lastSavedRevision = undefined;
        setStateValue("error", "Browser storage is unavailable.");
      });
  }
}
