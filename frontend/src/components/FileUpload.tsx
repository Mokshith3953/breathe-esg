import { useRef, useState } from "react";

interface FileUploadProps {
  accept?: string;
  label: string;
  hint?: string;
  onFile: (file: File) => void;
  disabled?: boolean;
}

export default function FileUpload({ accept, label, hint, onFile, disabled }: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleFile(file: File | undefined) {
    if (file) onFile(file);
  }

  return (
    <div
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (!disabled) handleFile(e.dataTransfer.files[0]);
      }}
      className={`
        relative border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
        ${dragging ? "border-brand-500 bg-brand-50" : "border-gray-300 hover:border-brand-400 hover:bg-gray-50"}
        ${disabled ? "opacity-50 cursor-not-allowed" : ""}
      `}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        disabled={disabled}
        onChange={(e) => handleFile(e.target.files?.[0])}
      />
      <div className="text-3xl mb-2">📁</div>
      <p className="text-sm font-medium text-gray-700">{label}</p>
      {hint && <p className="mt-1 text-xs text-gray-400">{hint}</p>}
      <p className="mt-2 text-xs text-gray-400">Drag & drop or click to browse</p>
    </div>
  );
}
