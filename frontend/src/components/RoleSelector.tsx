import type { UserOut } from "../api/client";

interface RoleSelectorProps {
  users: UserOut[];
  selectedUserId: string | null;
  onSelect: (userId: string) => void;
}

/** Test-only identity picker: every API call is made as the chosen seeded demo user. */
export default function RoleSelector({ users, selectedUserId, onSelect }: RoleSelectorProps) {
  if (users.length === 0) {
    return <span className="role-selector error">No users — is the backend in dev mode?</span>;
  }
  return (
    <label className="role-selector">
      <span>Acting as</span>
      <select value={selectedUserId ?? ""} onChange={(event) => onSelect(event.target.value)}>
        {users.map((user) => (
          <option key={user.id} value={user.id}>
            {user.role} — {user.username}
          </option>
        ))}
      </select>
    </label>
  );
}
