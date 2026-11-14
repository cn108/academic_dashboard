/**
 * Print a server-rendered HTML page (the report card) from a hidden same-page
 * frame. The document needs the auth header, so it arrives as a fetched string;
 * a popup window would be blocked by most browsers after an async fetch.
 *
 * Returns false when the browser refuses to give the frame a document.
 */
export function printHtmlDocument(html: string): boolean {
  const frame = document.createElement('iframe');
  frame.title = 'Report card';
  frame.style.position = 'fixed';
  frame.style.right = '0';
  frame.style.bottom = '0';
  frame.style.width = '0';
  frame.style.height = '0';
  frame.style.border = '0';
  document.body.appendChild(frame);

  const doc = frame.contentDocument;
  if (!doc) {
    frame.remove();
    return false;
  }

  doc.open();
  doc.write(html);
  doc.close();

  setTimeout(() => {
    frame.contentWindow?.focus();
    frame.contentWindow?.print();
    setTimeout(() => frame.remove(), 60000);
  }, 500);

  return true;
}
