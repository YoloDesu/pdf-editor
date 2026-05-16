import { EditPayload, PageData, PdfRect, TextBlock } from './pdf-editor.models';
import { pdfRectsOverlap } from './pdf-editor-geometry';

export function collectPageEditPayloads(page: PageData): EditPayload[] {
  return pageEditBlocks(page).map((block) => ({
    page_num: page.page_num,
    bbox: block.bbox,
    redaction_bbox: redactionBbox(block),
    old_text: block.text,
    new_text: block.editedText,
    font: block.font,
    size: block.size,
    color: block.color,
    bold: block.bold,
    italic: block.italic,
    insert_only: block.inserted
  }));
}

export function isTextBlockChanged(block: TextBlock): boolean {
  if (block.inserted) {
    return block.editedText.trim() !== '';
  }
  return block.editedText !== block.text || isMoved(block) || isStyleChanged(block);
}

function pageEditBlocks(page: PageData): TextBlock[] {
  const edited = page.text_blocks.filter((block) => isTextBlockChanged(block));
  const preserved = preservedNeighborBlocks(page.text_blocks, edited);
  return [...edited, ...preserved].sort((left, right) => left.originalIndex - right.originalIndex);
}

function preservedNeighborBlocks(blocks: TextBlock[], edited: TextBlock[]): TextBlock[] {
  const included = new Set(edited.map((block) => block.id));
  const preserved: TextBlock[] = [];
  let foundBlock = true;
  while (foundBlock) {
    foundBlock = addNextPreservedBlock(blocks, [...edited, ...preserved], included, preserved);
  }
  return preserved;
}

function addNextPreservedBlock(
  blocks: TextBlock[],
  redactingBlocks: TextBlock[],
  included: Set<string>,
  preserved: TextBlock[]
): boolean {
  const block = blocks.find((candidate) => shouldPreserveBlock(candidate, redactingBlocks, included));
  if (block === undefined) {
    return false;
  }
  included.add(block.id); preserved.push(block);
  return true;
}

function shouldPreserveBlock(
  block: TextBlock,
  redactingBlocks: TextBlock[],
  included: Set<string>
): boolean {
  if (included.has(block.id) || block.inserted) {
    return false;
  }
  return redactingBlocks.some((redactingBlock) => redactionTouchesBlock(redactingBlock, block));
}

function redactionTouchesBlock(redactingBlock: TextBlock, block: TextBlock): boolean {
  const redaction = redactionBbox(redactingBlock);
  if (redaction === null) {
    return false;
  }
  return pdfRectsOverlap(redaction, block.originalBbox);
}

function redactionBbox(block: TextBlock): PdfRect | null {
  if (block.inserted) {
    return null;
  }
  return block.originalBbox;
}

function isMoved(block: TextBlock): boolean {
  return block.bbox.some((value, index) => value !== block.originalBbox[index]);
}

function isStyleChanged(block: TextBlock): boolean {
  return block.font !== block.originalFont || block.size !== block.originalSize
    || block.bold !== block.originalBold || block.italic !== block.originalItalic;
}
