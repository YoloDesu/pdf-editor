import { AnalyzedPageData, AnalyzedTextBlock, PageData, PagePoint, TextBlock } from './pdf-editor.models';

export interface InsertTextBlockOptions {
  id: string;
  origin: PagePoint;
  width: number;
  height: number;
  font: string;
  size: number;
  bold: boolean;
  italic: boolean;
  originalIndex: number;
}

export function editablePageFromAnalysis(
  page: AnalyzedPageData,
  nextTextBlockId: () => string
): PageData {
  return {
    ...page,
    text_blocks: page.text_blocks.map((block, index) =>
      editableTextBlockFromAnalysis(block, index, nextTextBlockId()))
  };
}

function editableTextBlockFromAnalysis(
  block: AnalyzedTextBlock,
  originalIndex: number,
  id: string
): TextBlock {
  return {
    ...block, id, originalBbox: [...block.bbox],
    background_color: block.background_color ?? 16777215,
    originalFont: block.font, originalSize: block.size,
    originalBold: block.bold, originalItalic: block.italic,
    editedText: block.text, editing: false, moving: false, resizing: false,
    originalIndex, inserted: false
  };
}

export function insertedTextBlockFromOptions(options: InsertTextBlockOptions): TextBlock {
  const bbox = insertedTextBbox(options);
  return {
    id: options.id, bbox, originalBbox: [...bbox],
    text: '', font: options.font, size: options.size, color: 0,
    background_color: 16777215,
    originalFont: options.font, originalSize: options.size,
    bold: options.bold, italic: options.italic,
    originalBold: options.bold, originalItalic: options.italic,
    editedText: '', editing: true, moving: false, resizing: false,
    originalIndex: options.originalIndex, inserted: true
  };
}

function insertedTextBbox(options: InsertTextBlockOptions): [number, number, number, number] {
  return [
    options.origin.x,
    options.origin.y,
    options.origin.x + options.width,
    options.origin.y + options.height
  ];
}
