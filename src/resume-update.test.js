import { test } from "node:test";
import assert from "node:assert/strict";
import { applyResumeUpdate } from "./resume-update.js";

test("applies legacy changes without losing the existing resume", () => {
  const resume = { name: "Ada", summary: "Edited summary", skills: "Java" };
  assert.deepEqual(applyResumeUpdate(resume, { changes: { skills: "Python" } }), {
    name: "Ada", summary: "Edited summary", skills: "Python",
  });
  assert.deepEqual(applyResumeUpdate(resume, { changes: {} }), resume);
});

test("uses a normalized resume even when there are no changes", () => {
  const resume = { name: "Ada", personal_details: "duplicate" };
  const normalized = { name: "Ada", personal_details: "" };
  assert.deepEqual(applyResumeUpdate(resume, { changes: {}, resume: normalized }), normalized);
});

test("rejects malformed update responses", () => {
  const resume = { name: "Ada" };
  for (const data of [{}, { changes: null }, { changes: [] }, { changes: {}, resume: null }, { changes: {}, resume: [] }]) {
    assert.throws(() => applyResumeUpdate(resume, data), /invalid resume update/);
  }
});
