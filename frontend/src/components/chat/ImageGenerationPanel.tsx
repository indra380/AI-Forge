import { useState } from "react";

import type {
  GeneratedImageItem,
  ImageGenerateRequest,
  ImageSize,
  ImageStyle,
} from "../../types";

interface ImageGenerationPanelProps {
  disabled: boolean;
  threadId: string | null;
  sessionId: string | null;
  onEnsureSession: () => string;
  onGenerate: (request: ImageGenerateRequest) => Promise<GeneratedImageItem[]>;
}

const STYLE_OPTIONS: Array<{ label: string; value: ImageStyle }> = [
  { label: "Realistic", value: "realistic" },
  { label: "Anime", value: "anime" },
  { label: "Digital Art", value: "digital-art" },
  { label: "Cinematic", value: "cinematic" },
];

const SIZE_OPTIONS: Array<{ label: string; value: ImageSize }> = [
  { label: "Square 1024x1024", value: "1024x1024" },
  { label: "Portrait 1024x1536", value: "1024x1536" },
  { label: "Landscape 1536x1024", value: "1536x1024" },
];

export function ImageGenerationPanel({
  disabled,
  threadId,
  sessionId,
  onEnsureSession,
  onGenerate,
}: ImageGenerationPanelProps) {
  const [prompt, setPrompt] = useState("");
  const [style, setStyle] = useState<ImageStyle>("realistic");
  const [size, setSize] = useState<ImageSize>("1024x1024");
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gallery, setGallery] = useState<GeneratedImageItem[]>([]);

  const canGenerate = !disabled && !isGenerating && prompt.trim().length >= 3;

  async function runGenerate(nextPrompt?: string) {
    const promptToUse = (nextPrompt ?? prompt).trim();
    if (!promptToUse) return;

    setIsGenerating(true);
    setError(null);

    try {
      const resolvedSession = sessionId ?? onEnsureSession();
      const images = await onGenerate({
        prompt: promptToUse,
        style,
        size,
        threadId: threadId ?? undefined,
        sessionId: resolvedSession,
        imageCount: 1,
      });
      setGallery((prev) => [...images, ...prev].slice(0, 12));
      if (!nextPrompt) {
        setPrompt("");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Image generation failed");
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <section className="border-b border-slate-200 bg-white px-4 py-4">
      <div className="mx-auto w-full max-w-4xl rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
        <div className="mb-3">
          <h2 className="text-sm font-semibold text-slate-900">Image Generation</h2>
          <p className="text-xs text-slate-500">AI generates images from descriptions</p>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <select
            value={style}
            onChange={(event) => setStyle(event.target.value as ImageStyle)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
            disabled={disabled || isGenerating}
          >
            {STYLE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <select
            value={size}
            onChange={(event) => setSize(event.target.value as ImageSize)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
            disabled={disabled || isGenerating}
          >
            {SIZE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={() => void runGenerate()}
            disabled={!canGenerate}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isGenerating ? "Generating..." : "Generate Image"}
          </button>
        </div>

        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Describe an image to generate..."
          rows={2}
          className="mt-3 w-full resize-y rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
          disabled={disabled || isGenerating}
        />

        {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}

        {isGenerating ? (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, idx) => (
              <div key={idx} className="overflow-hidden rounded-xl border border-slate-200 bg-white">
                <div className="aspect-square animate-pulse bg-slate-200" />
                <div className="p-3">
                  <div className="mb-2 h-3 animate-pulse rounded bg-slate-200" />
                  <div className="h-3 w-2/3 animate-pulse rounded bg-slate-200" />
                </div>
              </div>
            ))}
          </div>
        ) : null}

        {gallery.length > 0 ? (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {gallery.map((image) => (
              <article key={image.imageId} className="overflow-hidden rounded-xl border border-slate-200 bg-white">
                <img src={image.imageUrl} alt={image.prompt} className="aspect-square w-full object-cover" />
                <div className="space-y-2 p-3">
                  <p className="line-clamp-2 text-xs text-slate-600">{image.prompt}</p>
                  <div className="flex items-center justify-between text-[11px] uppercase tracking-wide text-slate-400">
                    <span>{image.style}</span>
                    <span>{image.size}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <a
                      href={image.imageUrl}
                      download
                      className="rounded-lg border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
                    >
                      Download
                    </a>
                    <button
                      type="button"
                      onClick={() => void runGenerate(image.prompt)}
                      disabled={disabled || isGenerating}
                      className="rounded-lg bg-slate-900 px-2 py-1 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-40"
                    >
                      Regenerate
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
