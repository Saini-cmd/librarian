import { IconWarning, IconClose } from "../icons/Icon";

function formatResetTime(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export default function QuotaNotice({ quota, onDismiss }) {
  if (!quota) return null;

  const isIngest = quota.group === "ingest";
  const unit = isIngest ? "ingests" : "messages";
  const used = typeof quota.used === "number" ? quota.used : 0;
  const limit = typeof quota.limit === "number" ? quota.limit : 0;
  const resetTime = formatResetTime(quota.resets_at);

  return (
    <div role="alert" className="alert alert-warning alert-soft shadow-sm">
      <IconWarning className="w-5 h-5 shrink-0" />
      <div className="flex-1 min-w-0">
        <h3 className="text-sm font-semibold">Daily limit reached</h3>
        <p className="text-xs opacity-80">
          You&apos;ve used {used} of {limit} daily {unit}. More {unit} free up{" "}
          {resetTime ? `at ${resetTime}` : "later today"}.
        </p>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <span className="badge badge-warning badge-outline">
          {used} / {limit}
        </span>
        {onDismiss && (
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-circle"
            onClick={onDismiss}
            aria-label="Dismiss"
          >
            <IconClose className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}
