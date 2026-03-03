"use client";

import { useState, FormEvent } from "react";

const THEMES = [
  { value: "professional", label: "Professional" },
  { value: "modern", label: "Modern" },
  { value: "dark", label: "Dark" },
  { value: "creative", label: "Creative" },
  { value: "minimal", label: "Minimal" },
];

const PIPELINE_STEPS = [
  "Understanding your request…",
  "Researching content…",
  "Planning slide structure…",
  "Refining bullet points…",
  "Generating images…",
  "Reviewing presentation…",
  "Building PowerPoint file…",
];

export default function Home() {
  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  const [description, setDescription] = useState("");
  const [numSlides, setNumSlides] = useState(8);
  const [theme, setTheme] = useState("professional");
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setStep(0);

    // Simulate pipeline step progress
    const interval = setInterval(() => {
      setStep((prev) => (prev < PIPELINE_STEPS.length - 1 ? prev + 1 : prev));
    }, 8000);

    try {
      const res = await fetch("http://localhost:8000/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          topic,
          description,
          num_slides: numSlides,
          theme,
        }),
      });

      clearInterval(interval);

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Generation failed");
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${title.replace(/\s+/g, "_") || "presentation"}.pptx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
      clearInterval(interval);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-xl">
        {/* Header */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600 text-white">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
              />
            </svg>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            Agentic PPT Generator
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            AI-powered multi-agent presentation builder
          </p>
        </div>

        {/* Form Card */}
        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm"
        >
          {/* Title */}
          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Presentation Title
            </label>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Q4 Business Review"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* Topic */}
          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Topic
            </label>
            <input
              type="text"
              required
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. Revenue growth and market expansion"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* Description */}
          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Description{" "}
              <span className="font-normal text-gray-400">(optional)</span>
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Add any extra context or specific requirements…"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* Slides + Theme row */}
          <div className="mb-6 grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Number of Slides
              </label>
              <input
                type="number"
                min={3}
                max={20}
                value={numSlides}
                onChange={(e) => setNumSlides(parseInt(e.target.value) || 8)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Theme
              </label>
              <select
                value={theme}
                onChange={(e) => setTheme(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                {THEMES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? (
              <>
                <svg
                  className="h-4 w-4 animate-spin"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                  />
                </svg>
                Generating…
              </>
            ) : (
              "Generate Presentation"
            )}
          </button>
        </form>

        {/* Pipeline progress */}
        {loading && (
          <div className="mt-6 rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-400">
              Pipeline Progress
            </p>
            <div className="space-y-2">
              {PIPELINE_STEPS.map((label, i) => (
                <div key={i} className="flex items-center gap-3 text-sm">
                  {i < step ? (
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-green-100 text-green-600">
                      <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
                        <path
                          fillRule="evenodd"
                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                    </span>
                  ) : i === step ? (
                    <span className="flex h-5 w-5 items-center justify-center">
                      <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-blue-500" />
                    </span>
                  ) : (
                    <span className="flex h-5 w-5 items-center justify-center">
                      <span className="h-2 w-2 rounded-full bg-gray-200" />
                    </span>
                  )}
                  <span
                    className={
                      i < step
                        ? "text-green-700"
                        : i === step
                        ? "font-medium text-blue-700"
                        : "text-gray-400"
                    }
                  >
                    {label}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer */}
        <p className="mt-6 text-center text-xs text-gray-400">
          Powered by LangGraph &middot; OpenAI &middot; python-pptx
        </p>
      </div>
    </main>
  );
}
