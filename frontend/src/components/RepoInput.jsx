import { useState } from "react";

export default function RepoInput({ onProcess, disabled }) {
  const [repoLink, setRepoLink] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (repoLink.trim() && !disabled) {
      onProcess(repoLink.trim());
    }
  };

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-2xl mx-auto space-y-4">
      <p className="text-base-content/60 text-xs uppercase tracking-[0.15em] text-center">
        Paste a GitHub repository URL to begin
      </p>
      <div className="join w-full">
        <input
          type="text"
          value={repoLink}
          onChange={(e) => setRepoLink(e.target.value)}
          placeholder="https://github.com/owner/repo"
          className="input input-bordered join-item w-full font-mono text-sm"
          disabled={disabled}
        />
        <button
          type="submit"
          className="btn join-item px-8"
          disabled={disabled || !repoLink.trim()}
        >
          {disabled ? "Processing..." : "Process"}
        </button>
      </div>
    </form>
  );
}
