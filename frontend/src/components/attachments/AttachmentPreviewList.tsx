import type { PendingAttachment } from "../../types";

interface Props {
  attachments: PendingAttachment[];
  onRemove: (attachmentId: string) => void;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AttachmentPreviewList({ attachments, onRemove }: Props) {
  if (attachments.length === 0) {
    return null;
  }

  return (
    <div className="flex gap-3 overflow-x-auto pb-1">
      {attachments.map((attachment) => {
        const previewUrl = attachment.previewUrl ?? attachment.uploaded?.fileUrl;
        const type = attachment.uploaded?.attachmentType;
        const isImage = type === "image" && previewUrl;
        const isVideo = type === "video" && previewUrl;
        const badge = (type ?? "file").toUpperCase();

        return (
          <div
            key={attachment.id}
            className="flex min-w-[240px] max-w-[260px] shrink-0 gap-3 rounded-[20px] border border-slate-200 bg-white/90 p-3 shadow-sm"
          >
            {isImage ? (
              <img src={previewUrl} alt={attachment.file.name} className="h-16 w-16 shrink-0 rounded-2xl object-cover" />
            ) : null}
            {isVideo ? (
              <video src={previewUrl} className="h-16 w-16 shrink-0 rounded-2xl object-cover" muted />
            ) : null}

            <div className="mb-3 flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-slate-800">{attachment.file.name}</p>
                <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{formatSize(attachment.file.size)} • {badge}</p>
                <div className="mt-2 space-y-1.5">
                  <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className={`h-full rounded-full ${attachment.status === "error" ? "bg-red-500" : "bg-teal-600"}`}
                      style={{ width: `${attachment.progress}%` }}
                    />
                  </div>
                  <p className="text-xs font-medium text-slate-500">
                    {attachment.status === "uploading"
                      ? `Uploading ${attachment.progress}%`
                      : attachment.status === "error"
                        ? attachment.error ?? "Upload failed"
                        : `${attachment.uploaded?.attachmentType ?? "file"} ready`}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => onRemove(attachment.id)}
                className="shrink-0 rounded-full border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-600 transition hover:bg-slate-50"
              >
                Remove
              </button>
            </div>

            {!isImage && !isVideo ? (
              <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-slate-100 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                {type === "code" ? "Code" : type === "table" ? "Table" : type === "formula" ? "Math" : "File"}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}