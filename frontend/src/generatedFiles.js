import { unzipSync } from "fflate";

function describePdf(filename) {
  const basename = filename.split("/").at(-1);
  const examMatch = /^exam-version-([^.]+)\.pdf$/i.exec(basename);
  if (examMatch) {
    return {
      kind: "exam",
      version: examMatch[1],
      label: `מבחן – גרסה ${examMatch[1]}`,
    };
  }

  const answerKeyMatch = /^answer-key-([^.]+)\.pdf$/i.exec(basename);
  if (answerKeyMatch) {
    return {
      kind: "answer-key",
      version: answerKeyMatch[1],
      label: `מפתח תשובות – ${answerKeyMatch[1]}`,
    };
  }

  return { kind: "pdf", version: "", label: basename };
}

export function extractGeneratedPdfs(zipData) {
  const archive = unzipSync(
    zipData instanceof Uint8Array ? zipData : new Uint8Array(zipData),
  );
  return Object.entries(archive)
    .filter(([filename]) => filename.toLowerCase().endsWith(".pdf"))
    .map(([filename, bytes]) => ({
      filename,
      bytes,
      ...describePdf(filename),
    }))
    .sort((first, second) => (
      first.version.localeCompare(second.version, "en", { numeric: true })
      || (first.kind === "exam" ? -1 : 1)
    ));
}

export function revokeGeneratedPdfUrls(files, revokeObjectURL = URL.revokeObjectURL) {
  files.forEach((file) => revokeObjectURL(file.url));
}

export function createGeneratedPdfDownloads(
  zipData,
  createObjectURL = URL.createObjectURL,
  revokeObjectURL = URL.revokeObjectURL,
) {
  const downloads = [];
  try {
    for (const pdf of extractGeneratedPdfs(zipData)) {
      const blob = new Blob([pdf.bytes], { type: "application/pdf" });
      downloads.push({
        filename: pdf.filename,
        kind: pdf.kind,
        version: pdf.version,
        label: pdf.label,
        size: pdf.bytes.byteLength,
        url: createObjectURL(blob),
      });
    }
  } catch (error) {
    revokeGeneratedPdfUrls(downloads, revokeObjectURL);
    throw error;
  }
  return downloads;
}
