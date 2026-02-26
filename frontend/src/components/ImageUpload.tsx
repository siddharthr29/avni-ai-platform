import { useState, useRef, useCallback } from 'react';
import { ImageIcon, Camera, Upload, X, Loader2 } from 'lucide-react';
import clsx from 'clsx';

interface ImageUploadProps {
  onImageReady: (file: File) => void;
  compact?: boolean;
}

export function ImageUpload({ onImageReady, compact = false }: ImageUploadProps) {
  const [preview, setPreview] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const selectedFileRef = useRef<File | null>(null);

  const handleFile = useCallback((file: File) => {
    if (!file.type.startsWith('image/')) return;

    selectedFileRef.current = file;
    setFileName(file.name);

    const reader = new FileReader();
    reader.onload = (e) => {
      setPreview(e.target?.result as string);
    };
    reader.readAsDataURL(file);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleExtract = async () => {
    if (!selectedFileRef.current) return;
    setIsProcessing(true);
    try {
      onImageReady(selectedFileRef.current);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleClear = () => {
    setPreview(null);
    setFileName(null);
    selectedFileRef.current = null;
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (cameraInputRef.current) cameraInputRef.current.value = '';
  };

  if (compact) {
    return (
      <>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500"
          aria-label="Upload image"
          title="Upload image"
        >
          <ImageIcon className="w-5 h-5" />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={e => {
            const file = e.target.files?.[0];
            if (file) {
              handleFile(file);
              onImageReady(file);
            }
          }}
        />
      </>
    );
  }

  return (
    <div className="mt-2 rounded-lg border border-gray-200 bg-white p-4">
      {!preview ? (
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          className={clsx(
            'border-2 border-dashed rounded-lg p-6 text-center transition-colors',
            isDragging
              ? 'border-primary-400 bg-primary-50'
              : 'border-gray-300 hover:border-gray-400'
          )}
        >
          <Upload className="w-8 h-8 text-gray-400 mx-auto mb-2" />
          <p className="text-sm text-gray-600 mb-1">
            Drag and drop an image, or
          </p>
          <div className="flex items-center justify-center gap-2">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="text-sm text-primary-600 hover:text-primary-700 font-medium focus:outline-none focus:underline"
            >
              browse files
            </button>
            <span className="text-gray-400">|</span>
            <button
              onClick={() => cameraInputRef.current?.click()}
              className="flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700 font-medium focus:outline-none focus:underline"
            >
              <Camera className="w-4 h-4" />
              take photo
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            PNG, JPG, HEIC up to 10MB
          </p>
        </div>
      ) : (
        <div>
          <div className="relative inline-block">
            <img
              src={preview}
              alt="Uploaded preview"
              className="max-h-48 rounded-lg border border-gray-200"
            />
            <button
              onClick={handleClear}
              className="absolute -top-2 -right-2 p-1 bg-gray-800 text-white rounded-full hover:bg-gray-700 transition-colors"
              aria-label="Remove image"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          {fileName && (
            <p className="text-xs text-gray-500 mt-2">{fileName}</p>
          )}
          <div className="flex justify-end mt-3">
            <button
              onClick={handleExtract}
              disabled={isProcessing}
              className="flex items-center gap-2 px-4 py-1.5 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isProcessing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Extracting...
                </>
              ) : (
                'Extract Data'
              )}
            </button>
          </div>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={e => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={e => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />
    </div>
  );
}
