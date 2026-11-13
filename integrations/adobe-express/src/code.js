// The document side of the add-on. Adobe Express runs this file in its document sandbox; it is the only
// file that changes the design, and it makes no network call.
import addOnSandboxSdk from 'add-on-sdk-document-sandbox';
import { editor, constants } from 'express-document-sdk';

const { runtime } = addOnSandboxSdk.instance;

runtime.exposeApi({
  // block: { text, heads: [{ start, length }] } from linesToBlock() in api.js.
  // Adds one text block to the current page, 80% of the page wide, and returns how many characters it holds.
  addTextBlock(block) {
    const text = String((block && block.text) || '');
    if (!text) return 0;
    const parent = editor.context.insertionParent;
    const page = editor.context.currentPage;
    const pageWidth = (page && page.width) || 1080;
    const pageHeight = (page && page.height) || 1080;
    const width = Math.round(pageWidth * 0.8);
    const size = Math.max(12, Math.round(pageWidth / 54));

    const node = editor.createText(text);
    parent.children.append(node);
    node.fullContent.applyCharacterStyles({ fontSize: size });
    for (const h of block.heads || []) {
      node.fullContent.applyCharacterStyles(
        { fontSize: Math.round(size * 1.4) },
        { start: h.start, length: h.length },
      );
    }
    // Fixed width, so long lines wrap inside the page.
    node.layout = { type: constants.TextLayout.autoHeight, width };
    node.setPositionInParent(
      { x: pageWidth * 0.1, y: pageHeight * 0.08 },
      { x: node.boundsLocal.x, y: node.boundsLocal.y },
    );
    return text.length;
  },
});
