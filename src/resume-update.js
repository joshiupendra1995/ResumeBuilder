export function applyResumeUpdate(resume, data) {
  const changes = data.changes;
  if (!changes || typeof changes !== "object" || Array.isArray(changes)
      || (data.resume !== undefined && (!data.resume || typeof data.resume !== "object" || Array.isArray(data.resume)))) {
    throw new Error("The server returned an invalid resume update. Please try again.");
  }
  return data.resume === undefined ? { ...resume, ...changes } : data.resume;
}
