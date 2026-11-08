const KEY = "future-of-work-session";
const TTL = 12 * 60 * 60 * 1000;
let database;
let sessionId;

function open() {
  database ??= new Promise((resolve, reject) => {
    const request = indexedDB.open("future-of-work-public", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("sessions");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("Browser storage is busy"));
  });
  return database;
}

async function use(mode, action) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("sessions", mode);
    const request = action(tx.objectStore("sessions"));
    tx.oncomplete = () => resolve(request?.result);
    tx.onabort = () => reject(tx.error);
    tx.onerror = () => reject(tx.error);
  });
}

export async function restore() {
  sessionId = sessionStorage.getItem(KEY);
  const record = await use("readwrite", store => {
    const request = store.openCursor();
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) return;
      if (cursor.value.expires <= Date.now()) cursor.delete();
      cursor.continue();
    };
    if (sessionId) return store.get(sessionId);
  });
  if (record?.expires > Date.now() && record.schema === 1) return record;
}

export async function remember(result, file) {
  const nextId = sessionId || crypto.randomUUID();
  sessionStorage.setItem(KEY, nextId);
  sessionId = nextId;
  await use("readwrite", store => store.put({ schema: 1, result, file, expires: Date.now() + TTL }, nextId));
}

export async function forget() {
  if (sessionId) await use("readwrite", store => store.delete(sessionId));
  sessionStorage.removeItem(KEY);
  sessionId = undefined;
}
