import test from "node:test";
import assert from "node:assert/strict";
import { strToU8, zipSync } from "fflate";

import {
  createGeneratedPdfDownloads,
  extractGeneratedPdfs,
  revokeGeneratedPdfUrls,
} from "../src/generatedFiles.js";

function makeZip(filenames) {
  return zipSync(Object.fromEntries(
    filenames.map((filename) => [filename, strToU8(`%PDF-1.7 ${filename}`)]),
  ));
}

test("ZIP parsing extracts PDFs with their original filenames and Hebrew labels", () => {
  const files = extractGeneratedPdfs(makeZip([
    "exam-version-A.pdf",
    "answer-key-A.pdf",
  ]));

  assert.deepEqual(files.map(({ filename, label }) => ({ filename, label })), [
    { filename: "exam-version-A.pdf", label: "מבחן – גרסה A" },
    { filename: "answer-key-A.pdf", label: "מפתח תשובות – A" },
  ]);
});

test("separate mode files are presented individually", () => {
  const files = extractGeneratedPdfs(makeZip([
    "exam-version-A.pdf",
    "answer-key-A.pdf",
  ]));
  assert.deepEqual(files.map((file) => file.filename), [
    "exam-version-A.pdf",
    "answer-key-A.pdf",
  ]);
});

test("appended mode presents only the exam PDF", () => {
  const files = extractGeneratedPdfs(makeZip(["exam-version-A.pdf"]));
  assert.deepEqual(files.map((file) => file.filename), ["exam-version-A.pdf"]);
});

test("both mode presents the appended exam and separate answer key", () => {
  const files = extractGeneratedPdfs(makeZip([
    "exam-version-A.pdf",
    "answer-key-A.pdf",
  ]));
  assert.deepEqual(files.map((file) => file.kind), ["exam", "answer-key"]);
});

test("multiple versions are ordered by version with exam before answer key", () => {
  const files = extractGeneratedPdfs(makeZip([
    "answer-key-B.pdf",
    "exam-version-A.pdf",
    "exam-version-B.pdf",
    "answer-key-A.pdf",
  ]));
  assert.deepEqual(files.map((file) => file.filename), [
    "exam-version-A.pdf",
    "answer-key-A.pdf",
    "exam-version-B.pdf",
    "answer-key-B.pdf",
  ]);
});

test("non-PDF and nested ZIP entries are never presented as downloads", () => {
  const files = extractGeneratedPdfs(zipSync({
    "exam-version-A.pdf": strToU8("%PDF exam"),
    "exam-versions.zip": strToU8("not a primary download"),
    "notes.txt": strToU8("notes"),
  }));
  assert.deepEqual(files.map((file) => file.filename), ["exam-version-A.pdf"]);
});

test("download URLs are created for PDFs and can all be revoked", () => {
  const created = [];
  const revoked = [];
  const files = createGeneratedPdfDownloads(
    makeZip(["exam-version-A.pdf", "answer-key-A.pdf"]),
    (blob) => {
      assert.equal(blob.type, "application/pdf");
      const url = `blob:test-${created.length + 1}`;
      created.push(url);
      return url;
    },
    (url) => revoked.push(url),
  );

  assert.deepEqual(files.map((file) => file.url), created);
  revokeGeneratedPdfUrls(files, (url) => revoked.push(url));
  assert.deepEqual(revoked, created);
});
