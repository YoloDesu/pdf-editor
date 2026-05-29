import { CommonModule } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { editorApiUrl } from './pdf-editor-api-url';
import { collectPageEditPayloads, isTextBlockChanged } from './pdf-editor-edits';
import { clampedTextOrigin, constrainedBbox, constrainedResizedBbox, draggedBbox, pagePointFromMouseEvent, resizedBbox, textDragStateFromPointer, textResizeStateFromPointer } from './pdf-editor-geometry';
import { editablePageFromAnalysis, insertedTextBlockFromOptions } from './pdf-editor-page-state';
import { editorFonts } from './pdf-editor-fonts';
import { AnalyzedPageData, DocumentData, EditPayload, PageData, TextBlock, TextDragState, TextResizeEdge, TextResizeState, UploadResponse } from './pdf-editor.models';

export type { PageData } from './pdf-editor.models';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent implements OnDestroy {
  private readonly http = inject(HttpClient);

  readonly apiUrl = editorApiUrl(window.location);

  docId: string | null = null;
  pages: PageData[] = [];
  currentPageIndex = 0;
  currentPageImageUrl = '';

  uploading = false;
  saving = false;
  previewing = false;
  addingText = false;
  selectedFont = 'Helvetica';
  selectedFontSize = 12;
  selectedBold = false; selectedItalic = false;
  activeBlock: TextBlock | null = null;

  readonly commonFonts = editorFonts;

  private previewTimerId: number | null = null;
  private previewObjectUrl: string | null = null;
  private previewRequestId = 0;
  private imageVersion = 0;
  private nextTextBlockId = 0;
  private dragState: TextDragState | null = null;
  private resizeState: TextResizeState | null = null;
  private readonly dragMove = (event: PointerEvent): void => this.moveDraggedText(event);
  private readonly dragEnd = (): void => this.finishTextDrag();
  private readonly resizeMove = (event: PointerEvent): void => this.resizeDraggedText(event);
  private readonly resizeEnd = (): void => this.finishTextResize();

  get currentPage(): PageData | null {
    return this.pages[this.currentPageIndex] ?? null;
  }
  ngOnDestroy(): void {
    this.clearPreviewTimer();
    this.removeDragListeners();
    this.removeResizeListeners();
    this.revokePreviewObjectUrl();
  }
  onFileSelected(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (file === undefined) {
      return;
    }
    this.uploadPdf(file);
  }

  uploadPdf(file: File): void {
    this.uploading = true;
    const formData = new FormData();
    formData.append('file', file);

    this.http.post<UploadResponse>(`${this.apiUrl}/upload`, formData).subscribe({
      next: (response) => this.handleUploadResponse(response),
      error: (error) => this.handleUploadError(error)
    });
  }
  fetchPages(): void {
    if (this.docId === null) {
      return;
    }

    this.http.get<DocumentData>(`${this.apiUrl}/document/${this.docId}/pages`).subscribe({
      next: (response) => this.loadAnalyzedPages(response.pages),
      error: (error) => this.handlePageLoadError(error)
    });
  }

  nextPage(): void {
    if (this.currentPageIndex >= this.pages.length - 1) {
      return;
    }
    this.showPage(this.currentPageIndex + 1);
  }
  prevPage(): void {
    if (this.currentPageIndex <= 0) {
      return;
    }
    this.showPage(this.currentPageIndex - 1);
  }

  selectPage(pageIndex: number): void {
    if (pageIndex === this.currentPageIndex) {
      return;
    }
    this.showPage(pageIndex);
  }

  queuePreviewRefresh(delayMs = 250): void {
    this.clearPreviewTimer();
    this.previewTimerId = window.setTimeout(() => this.refreshPreview(), delayMs);
  }

  queueBlockPreview(block: TextBlock): void {
    if (block.editing) {
      return;
    }
    this.queuePreviewRefresh();
  }

  textBlockBackground(block: TextBlock): string | null {
    if (!block.editing || block.inserted) {
      return null;
    }
    return this.pdfColor(block.background_color);
  }

  collectPendingEdits(): EditPayload[] {
    return this.pages.flatMap((page) => this.collectPageEdits(page));
  }

  isChanged(block: TextBlock): boolean {
    return isTextBlockChanged(block);
  }

  focusTextBlock(block: TextBlock): void {
    block.editing = true; this.activeBlock = block;
    this.selectedFont = block.font; this.selectedFontSize = block.size;
    this.selectedBold = block.bold; this.selectedItalic = block.italic;
  }

  applySelectedTextStyle(): void {
    if (this.activeBlock === null) {
      return;
    }
    this.activeBlock.font = this.selectedFont; this.activeBlock.size = this.selectedFontSize;
    this.activeBlock.bold = this.selectedBold; this.activeBlock.italic = this.selectedItalic;
    if (this.activeBlock.editing) {
      return;
    }
    this.queuePreviewRefresh(0);
  }

  toggleSelectedBold(): void {
    this.selectedBold = !this.selectedBold; this.applySelectedTextStyle();
  }

  toggleSelectedItalic(): void {
    this.selectedItalic = !this.selectedItalic; this.applySelectedTextStyle();
  }

  toggleAddText(): void {
    this.addingText = !this.addingText;
  }

  handlePageClick(event: MouseEvent, page: PageData): void {
    if (!this.addingText || event.target instanceof HTMLTextAreaElement) {
      return;
    }

    const point = pagePointFromMouseEvent(event, page);
    const block = this.insertTextBlockAt(page, point.x, point.y);
    this.focusInsertedBlock(block.id);
  }

  finishBlockEditing(page: PageData, block: TextBlock): void {
    block.editing = false;
    if (block.moving || block.resizing) {
      return;
    }
    if (block.inserted && block.editedText.trim() !== '') {
      this.queuePreviewRefresh(0);
      return;
    }
    if (block.inserted) {
      this.removeTextBlock(page, block);
      return;
    }
    if (isTextBlockChanged(block)) {
      this.queuePreviewRefresh(0);
    }
  }

  startTextDrag(event: PointerEvent, page: PageData, block: TextBlock): void {
    const pageElement = this.pageElementFromEvent(event);
    if (pageElement === null) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    block.moving = true;
    this.dragState = textDragStateFromPointer(event, pageElement, page, block);
    this.addDragListeners();
  }

  startTextResize(event: PointerEvent, page: PageData, block: TextBlock, edge: TextResizeEdge): void {
    const pageElement = this.pageElementFromEvent(event);
    if (pageElement === null) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    block.resizing = true;
    this.resizeState = textResizeStateFromPointer(event, pageElement, page, block, edge);
    this.addResizeListeners();
  }

  saveDocument(): void {
    if (this.docId === null) {
      return;
    }

    const edits = this.collectPendingEdits();
    if (edits.length === 0) {
      window.alert('No changes to save.');
      return;
    }

    this.downloadEditedDocument(edits);
  }

  private handleUploadResponse(response: UploadResponse): void {
    this.docId = response.doc_id;
    this.pages = [];
    this.currentPageImageUrl = '';
    this.fetchPages();
  }

  private handleUploadError(error: unknown): void {
    console.error('Upload failed', error);
    window.alert(`Upload failed: ${this.errorMessage(error)}`);
    this.uploading = false;
  }

  private loadAnalyzedPages(pages: AnalyzedPageData[]): void {
    this.pages = pages.map((page) => this.preparePageForEditing(page));
    this.uploading = false;
    this.showPage(0);
  }

  private handlePageLoadError(error: unknown): void {
    console.error('Failed to fetch pages', error);
    window.alert(`Failed to analyze document: ${this.errorMessage(error)}`);
    this.uploading = false;
  }

  private preparePageForEditing(page: AnalyzedPageData): PageData {
    return editablePageFromAnalysis(page, () => this.newTextBlockId());
  }

  private showPage(pageIndex: number): void {
    this.currentPageIndex = pageIndex;
    this.queuePreviewRefresh(0);
  }

  private refreshPreview(): void {
    const page = this.currentPage;
    if (this.docId === null || page === null) {
      return;
    }

    const edits = this.collectPageEdits(page);
    if (edits.length === 0) {
      this.showOriginalPageImage(page);
      return;
    }
    this.requestPreviewImage(page, edits);
  }

  private collectPageEdits(page: PageData): EditPayload[] {
    return collectPageEditPayloads(page);
  }

  private insertTextBlockAt(page: PageData, x: number, y: number): TextBlock {
    const block = this.newInsertedTextBlock(page, x, y);
    page.text_blocks.push(block);
    return block;
  }

  private newInsertedTextBlock(page: PageData, x: number, y: number): TextBlock {
    const height = this.selectedFontSize * 1.5;
    const origin = clampedTextOrigin(page, x, y, height);
    const width = Math.min(220, page.width - origin.x);
    return insertedTextBlockFromOptions({
      id: this.newTextBlockId(), origin, width, height,
      font: this.selectedFont, size: this.selectedFontSize,
      bold: this.selectedBold, italic: this.selectedItalic,
      originalIndex: page.text_blocks.length
    });
  }

  private focusInsertedBlock(blockId: string): void {
    window.setTimeout(() => {
      const selector = `[data-block-id="${blockId}"]`;
      const textarea = document.querySelector<HTMLTextAreaElement>(selector);
      textarea?.focus();
    });
  }

  private removeTextBlock(page: PageData, block: TextBlock): void {
    page.text_blocks = page.text_blocks.filter((candidate) => candidate.id !== block.id);
    this.queuePreviewRefresh(0);
  }

  private newTextBlockId(): string {
    this.nextTextBlockId++;
    return `text-block-${this.nextTextBlockId}`;
  }

  private pdfColor(color: number): string {
    const sanitized = Math.max(0, Math.min(color, 16777215));
    return `#${sanitized.toString(16).padStart(6, '0')}`;
  }

  private pageElementFromEvent(event: PointerEvent): HTMLElement | null {
    const target = event.currentTarget as HTMLElement;
    return target.closest('.page-container');
  }

  private addDragListeners(): void {
    window.addEventListener('pointermove', this.dragMove);
    window.addEventListener('pointerup', this.dragEnd);
  }

  private removeDragListeners(): void {
    window.removeEventListener('pointermove', this.dragMove);
    window.removeEventListener('pointerup', this.dragEnd);
  }

  private addResizeListeners(): void {
    window.addEventListener('pointermove', this.resizeMove);
    window.addEventListener('pointerup', this.resizeEnd);
  }

  private removeResizeListeners(): void {
    window.removeEventListener('pointermove', this.resizeMove);
    window.removeEventListener('pointerup', this.resizeEnd);
  }

  private moveDraggedText(event: PointerEvent): void {
    if (this.dragState === null) {
      return;
    }

    const bbox = draggedBbox(event, this.dragState);
    this.dragState.block.bbox = constrainedBbox(bbox, this.dragState.page);
    this.queuePreviewRefresh();
  }

  private finishTextDrag(): void {
    if (this.dragState === null) {
      return;
    }
    this.dragState.block.moving = false;
    this.dragState = null;
    this.removeDragListeners();
    this.queuePreviewRefresh(0);
  }

  private resizeDraggedText(event: PointerEvent): void {
    if (this.resizeState === null) {
      return;
    }

    const bbox = resizedBbox(event, this.resizeState);
    this.resizeState.block.bbox = constrainedResizedBbox(bbox, this.resizeState.page);
    this.queuePreviewRefresh();
  }

  private finishTextResize(): void {
    if (this.resizeState === null) {
      return;
    }
    this.resizeState.block.resizing = false;
    this.resizeState = null;
    this.removeResizeListeners();
    this.queuePreviewRefresh(0);
  }

  private showOriginalPageImage(page: PageData): void {
    this.previewRequestId++;
    this.previewing = false;
    this.setPageImageUrl(this.originalPageImageUrl(page));
  }

  private originalPageImageUrl(page: PageData): string {
    this.imageVersion++;
    return `${this.apiUrl}/document/${this.docId}/page/${page.page_num}/image?v=${this.imageVersion}`;
  }

  private requestPreviewImage(page: PageData, edits: EditPayload[]): void {
    const requestId = ++this.previewRequestId;
    this.previewing = true;
    const url = `${this.apiUrl}/document/${this.docId}/page/${page.page_num}/preview`;

    this.http.post(url, { edits }, { responseType: 'blob' }).subscribe({
      next: (blob) => this.usePreviewBlob(requestId, blob),
      error: () => this.handlePreviewError(requestId)
    });
  }

  private usePreviewBlob(requestId: number, blob: Blob): void {
    if (requestId !== this.previewRequestId) {
      return;
    }
    this.previewing = false;
    this.setPreviewObjectUrl(window.URL.createObjectURL(blob));
  }

  private handlePreviewError(requestId: number): void {
    if (requestId !== this.previewRequestId) {
      return;
    }
    this.previewing = false;
    window.alert('Failed to render live preview');
  }

  private setPreviewObjectUrl(url: string): void {
    this.revokePreviewObjectUrl();
    this.previewObjectUrl = url;
    this.currentPageImageUrl = url;
  }

  private setPageImageUrl(url: string): void {
    this.revokePreviewObjectUrl();
    this.currentPageImageUrl = url;
  }

  private revokePreviewObjectUrl(): void {
    if (this.previewObjectUrl === null) {
      return;
    }
    window.URL.revokeObjectURL(this.previewObjectUrl);
    this.previewObjectUrl = null;
  }

  private clearPreviewTimer(): void {
    if (this.previewTimerId === null) {
      return;
    }
    window.clearTimeout(this.previewTimerId);
    this.previewTimerId = null;
  }

  private downloadEditedDocument(edits: EditPayload[]): void {
    this.saving = true;
    this.http.post(`${this.apiUrl}/document/${this.docId}/save`, { edits }, {
      responseType: 'blob'
    }).subscribe({
      next: (blob) => this.downloadPdfBlob(blob),
      error: () => this.handleSaveError()
    });
  }

  private downloadPdfBlob(blob: Blob): void {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `edited_${this.docId}.pdf`;
    link.click();
    window.URL.revokeObjectURL(url);
    this.saving = false;
  }

  private handleSaveError(): void {
    console.error('Failed to save document');
    window.alert('Failed to save changes');
    this.saving = false;
  }

  private errorMessage(error: unknown): string {
    if (!(error instanceof HttpErrorResponse)) {
      return error instanceof Error ? error.message : 'Unexpected error';
    }
    const body = error.error;
    const record = body as Record<string, unknown> | null;
    if (record !== null && typeof record === 'object' && typeof record['detail'] === 'string') {
      return record['detail'];
    }
    return typeof body === 'string' && body.trim() !== '' ? body : error.message;
  }
}
