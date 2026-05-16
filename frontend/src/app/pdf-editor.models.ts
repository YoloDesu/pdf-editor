export type PdfRect = [number, number, number, number];

export interface TextBlock {
  id: string;
  bbox: PdfRect;
  originalBbox: PdfRect;
  text: string;
  font: string;
  size: number;
  color: number;
  background_color: number;
  originalFont: string;
  originalSize: number;
  bold: boolean;
  italic: boolean;
  originalBold: boolean;
  originalItalic: boolean;
  editedText: string;
  editing: boolean;
  moving: boolean;
  resizing: boolean;
  originalIndex: number;
  inserted: boolean;
}

export interface AnalyzedTextBlock {
  bbox: PdfRect;
  text: string;
  font: string;
  size: number;
  color: number;
  background_color: number;
  bold: boolean;
  italic: boolean;
}

export interface PageData {
  page_num: number;
  width: number;
  height: number;
  text_blocks: TextBlock[];
}

export interface DocumentData {
  pages: AnalyzedPageData[];
}

export interface AnalyzedPageData {
  page_num: number;
  width: number;
  height: number;
  text_blocks: AnalyzedTextBlock[];
}

export interface UploadResponse {
  doc_id: string;
}

export interface EditPayload {
  page_num: number;
  bbox: PdfRect;
  redaction_bbox: PdfRect | null;
  old_text: string;
  new_text: string;
  font: string;
  size: number;
  color: number;
  bold: boolean;
  italic: boolean;
  insert_only: boolean;
}

export interface PagePoint {
  x: number;
  y: number;
}

export interface TextDragState {
  page: PageData;
  block: TextBlock;
  startClientX: number;
  startClientY: number;
  startBbox: PdfRect;
  pageBounds: DOMRect;
}

export type TextResizeEdge = 'right' | 'bottom' | 'corner';

export interface TextResizeState {
  page: PageData;
  block: TextBlock;
  edge: TextResizeEdge;
  startClientX: number;
  startClientY: number;
  startBbox: PdfRect;
  pageBounds: DOMRect;
}
