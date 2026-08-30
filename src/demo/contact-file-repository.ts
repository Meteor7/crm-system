import type { StoredContactFile } from './binary-storage'

const DATABASE_NAME = 'semiconductor-crm-contact-files'
const STORE_NAME = 'contact-files'

export interface ContactFileRepository {
  list(contactId: string): Promise<StoredContactFile[]>
  get(id: string): Promise<StoredContactFile | undefined>
  save(file: StoredContactFile): Promise<void>
  remove(id: string): Promise<void>
  reassignContact(fromContactId: string, toContactId: string): Promise<void>
  removeForContact(contactId: string): Promise<void>
}

function cloneFile(file: StoredContactFile): StoredContactFile {
  const { blob, ...meta } = file
  return { ...structuredClone(meta), blob }
}

export function createMemoryContactFileRepository(
  initialFiles: StoredContactFile[] = [],
): ContactFileRepository {
  const files = initialFiles.map(cloneFile)
  return {
    async list(contactId) {
      return files.filter((file) => file.contactId === contactId).map(cloneFile)
    },
    async get(id) {
      const file = files.find((item) => item.id === id)
      return file ? cloneFile(file) : undefined
    },
    async save(file) {
      const index = files.findIndex((item) => item.id === file.id)
      if (index >= 0) files[index] = cloneFile(file)
      else files.push(cloneFile(file))
    },
    async remove(id) {
      const index = files.findIndex((item) => item.id === id)
      if (index >= 0) files.splice(index, 1)
    },
    async reassignContact(fromContactId, toContactId) {
      for (const file of files) {
        if (file.contactId === fromContactId) file.contactId = toContactId
      }
    },
    async removeForContact(contactId) {
      for (let index = files.length - 1; index >= 0; index -= 1) {
        if (files[index].contactId === contactId) files.splice(index, 1)
      }
    },
  }
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('联系人文件存储失败'))
  })
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error ?? new Error('联系人文件事务失败'))
    transaction.onabort = () => reject(transaction.error ?? new Error('联系人文件事务已取消'))
  })
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, 1)
    request.onupgradeneeded = () => {
      const store = request.result.createObjectStore(STORE_NAME, { keyPath: 'id' })
      store.createIndex('contactId', 'contactId', { unique: false })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('无法打开联系人文件存储'))
  })
}

function createIndexedDbContactFileRepository(): ContactFileRepository {
  return {
    async list(contactId) {
      const database = await openDatabase()
      try {
        const transaction = database.transaction(STORE_NAME, 'readonly')
        const files = await requestResult(
          transaction.objectStore(STORE_NAME).index('contactId').getAll(contactId),
        ) as StoredContactFile[]
        await transactionDone(transaction)
        return files.map(cloneFile)
      } finally {
        database.close()
      }
    },
    async get(id) {
      const database = await openDatabase()
      try {
        const transaction = database.transaction(STORE_NAME, 'readonly')
        const file = await requestResult(
          transaction.objectStore(STORE_NAME).get(id),
        ) as StoredContactFile | undefined
        await transactionDone(transaction)
        return file ? cloneFile(file) : undefined
      } finally {
        database.close()
      }
    },
    async save(file) {
      const database = await openDatabase()
      try {
        const transaction = database.transaction(STORE_NAME, 'readwrite')
        transaction.objectStore(STORE_NAME).put(cloneFile(file))
        await transactionDone(transaction)
      } finally {
        database.close()
      }
    },
    async remove(id) {
      const database = await openDatabase()
      try {
        const transaction = database.transaction(STORE_NAME, 'readwrite')
        transaction.objectStore(STORE_NAME).delete(id)
        await transactionDone(transaction)
      } finally {
        database.close()
      }
    },
    async reassignContact(fromContactId, toContactId) {
      const database = await openDatabase()
      try {
        const transaction = database.transaction(STORE_NAME, 'readwrite')
        const store = transaction.objectStore(STORE_NAME)
        const files = await requestResult(store.index('contactId').getAll(fromContactId)) as StoredContactFile[]
        for (const file of files) store.put({ ...file, contactId: toContactId })
        await transactionDone(transaction)
      } finally {
        database.close()
      }
    },
    async removeForContact(contactId) {
      const database = await openDatabase()
      try {
        const transaction = database.transaction(STORE_NAME, 'readwrite')
        const store = transaction.objectStore(STORE_NAME)
        const keys = await requestResult(store.index('contactId').getAllKeys(contactId))
        for (const key of keys) store.delete(key)
        await transactionDone(transaction)
      } finally {
        database.close()
      }
    },
  }
}

let sharedRepository: ContactFileRepository | undefined

export function getSharedContactFileRepository(): ContactFileRepository {
  sharedRepository ??= typeof indexedDB === 'undefined'
    ? createMemoryContactFileRepository()
    : createIndexedDbContactFileRepository()
  return sharedRepository
}
