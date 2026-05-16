import { PageData, PagePoint, PdfRect, TextDragState, TextResizeState } from './pdf-editor.models';

export function pagePointFromMouseEvent(event: MouseEvent, page: PageData): PagePoint {
  const target = event.currentTarget as HTMLElement;
  const bounds = target.getBoundingClientRect();
  return {
    x: ((event.clientX - bounds.left) / bounds.width) * page.width,
    y: ((event.clientY - bounds.top) / bounds.height) * page.height
  };
}

export function clampedTextOrigin(
  page: PageData,
  x: number,
  y: number,
  height: number
): PagePoint {
  return {
    x: Math.max(0, Math.min(x, page.width - 80)),
    y: Math.max(0, Math.min(y, page.height - height))
  };
}

export function draggedBbox(event: PointerEvent, drag: TextDragState): PdfRect {
  const delta = dragDelta(event, drag);
  return [
    drag.startBbox[0] + delta.x,
    drag.startBbox[1] + delta.y,
    drag.startBbox[2] + delta.x,
    drag.startBbox[3] + delta.y
  ];
}

export function constrainedBbox(bbox: PdfRect, page: PageData): PdfRect {
  const width = bbox[2] - bbox[0];
  const height = bbox[3] - bbox[1];
  const x0 = Math.max(0, Math.min(bbox[0], page.width - width));
  const y0 = Math.max(0, Math.min(bbox[1], page.height - height));
  return [x0, y0, x0 + width, y0 + height];
}

export function resizedBbox(event: PointerEvent, resize: TextResizeState): PdfRect {
  const delta = dragDelta(event, resize);
  const bbox: PdfRect = [...resize.startBbox];
  if (resize.edge === 'right' || resize.edge === 'corner') {
    bbox[2] += delta.x;
  }
  if (resize.edge === 'bottom' || resize.edge === 'corner') {
    bbox[3] += delta.y;
  }
  return bbox;
}

export function constrainedResizedBbox(bbox: PdfRect, page: PageData): PdfRect {
  const minimumWidth = 12;
  const minimumHeight = 8;
  const x1 = Math.max(bbox[0] + minimumWidth, Math.min(bbox[2], page.width));
  const y1 = Math.max(bbox[1] + minimumHeight, Math.min(bbox[3], page.height));
  return [bbox[0], bbox[1], x1, y1];
}

export function pdfRectsOverlap(first: PdfRect, second: PdfRect): boolean {
  const overlapsHorizontally = first[0] < second[2] && first[2] > second[0];
  const overlapsVertically = first[1] < second[3] && first[3] > second[1];
  return overlapsHorizontally && overlapsVertically;
}

function dragDelta(event: PointerEvent, drag: TextDragState | TextResizeState): PagePoint {
  return {
    x: ((event.clientX - drag.startClientX) / drag.pageBounds.width) * drag.page.width,
    y: ((event.clientY - drag.startClientY) / drag.pageBounds.height) * drag.page.height
  };
}
