import type { DragEvent } from "react";

interface Props {
  disabled: boolean;
  onBrowse: () => void;
  onFilesSelected: (files: FileList | File[]) => void;
}

export function AttachmentDropzone({ disabled, onBrowse, onFilesSelected }: Props) {
  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (disabled) return;
    onFilesSelected(event.dataTransfer.files);
  }

  return (
    <div
      onDragOver={(event) => event.preventDefault()}
      onDrop={handleDrop}
      className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4"
    >
      <div className="flex flex-col gap-2 text-sm text-slate-600 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="font-semibold text-slate-800">Attachments</p>
          <p className="text-xs text-slate-500">Images, videos, tables, code, docs, and formulas</p>
        </div>
        <button
          type="button"
          onClick={onBrowse}
          disabled={disabled}
          className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Upload Files
        </button>
      </div>
      <p className="mt-3 text-xs text-slate-500">
        Drag and drop files here, or browse to attach images, videos, tables, documents, code, and LaTeX files.
      </p>
    </div>
  );
}