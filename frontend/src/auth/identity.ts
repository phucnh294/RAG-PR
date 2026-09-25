// Test identity for the role picker: the id of a seeded demo user, sent on every API
// call as X-User-Id. The backend loads the user and role from its database — the UI
// never sends a role — so this is swapped for a real login token later without touching
// the pages.

const STORAGE_KEY = "rag.selectedUserId";
export const USER_ID_HEADER = "X-User-Id";

let currentUserId: string | null = readStoredUserId();

function readStoredUserId(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function getSelectedUserId(): string | null {
  return currentUserId;
}

export function setSelectedUserId(userId: string): void {
  currentUserId = userId;
  try {
    window.localStorage.setItem(STORAGE_KEY, userId);
  } catch {
    // Storage blocked (private mode): the choice still holds for this page load.
  }
}

export function authHeaders(): Record<string, string> {
  return currentUserId ? { [USER_ID_HEADER]: currentUserId } : {};
}
