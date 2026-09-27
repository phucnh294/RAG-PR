/** Opens a text file of an agents run (test-case.md, result.json, a handoff .md) in a new
 * tab. Files go through apiFetch (X-User-Id header), so a plain <a href> cannot be used. */
export default function RunFileLink({
  load,
  name,
  label,
}: {
  load: () => Promise<Blob>;
  name: string;
  label: string;
}) {
  async function open() {
    const blob = await load();
    const url = URL.createObjectURL(new Blob([await blob.text()], { type: "text/plain" }));
    window.open(url, "_blank", "noopener");
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }
  return (
    <button className="agent-link-button" onClick={open} title={name}>
      {label}
    </button>
  );
}
