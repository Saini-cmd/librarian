import { useEffect, useState } from "react";
import { useAuth, useUser } from "@clerk/clerk-react";
import { useNavigate } from "react-router-dom";
import { getProfile, updateProfile } from "../api/client";

export default function SettingsPage() {
  const { user } = useUser();
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [name, setName] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getProfile()
      .then((data) => {
        setProfile(data);
        setName(data.name || "");
      })
      .catch(() => {});
  }, []);

  async function handleSave(e) {
    e.preventDefault();
    try {
      await updateProfile({ name });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {}
  }

  return (
    <div className="min-h-screen bg-base-100 text-base-content">
      <div className="max-w-2xl mx-auto px-6 py-12 space-y-8">
        <button
          className="btn btn-ghost btn-sm font-mono text-xs uppercase tracking-wider"
          onClick={() => navigate("/app")}
        >
          &larr; Back to App
        </button>

        <div className="border-2 border-base-300 p-8 space-y-6">
          <h1 className="text-2xl font-black uppercase tracking-tight">
            Settings
          </h1>

          <div className="space-y-2">
            <p className="font-mono text-xs uppercase tracking-widest text-base-content/50">
              Account
            </p>
            <p className="font-mono text-sm text-base-content/70">
              {user?.primaryEmailAddress?.emailAddress || "No email"}
            </p>
          </div>

          <form onSubmit={handleSave} className="space-y-4">
            <div className="space-y-2">
              <label className="font-mono text-xs uppercase tracking-widest text-base-content/50">
                Display Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="input input-bordered w-full font-mono text-sm"
                placeholder="Your name"
              />
            </div>

            <div className="flex items-center gap-4">
              <button type="submit" className="btn">
                Save
              </button>
              {saved && (
                <span className="font-mono text-xs text-success uppercase tracking-wider">
                  Saved
                </span>
              )}
            </div>
          </form>

          <hr className="border-base-300" />

          <button
            className="btn btn-outline text-xs font-mono uppercase tracking-wider"
            onClick={() => signOut()}
          >
            Sign Out
          </button>
        </div>
      </div>
    </div>
  );
}
