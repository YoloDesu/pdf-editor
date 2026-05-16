import { constrainedResizedBbox, resizedBbox } from './pdf-editor-geometry';
import { PageData, PdfRect, TextBlock, TextResizeState } from './pdf-editor.models';

describe('PDF editor geometry', () => {
  it('should resize a text box from the corner in page coordinates', () => {
    const resize = resizeState('corner');

    const resized = resizedBbox(pointerEventAt(120, 110), resize);
    const constrained = constrainedResizedBbox(resized, resize.page);

    expect(constrained).toEqual([10, 10, 90, 40]);
  });

  it('should keep resized text boxes inside the page', () => {
    const resize = resizeState('right');

    const resized = resizedBbox(pointerEventAt(500, 100), resize);
    const constrained = constrainedResizedBbox(resized, resize.page);

    expect(constrained).toEqual([10, 10, 200, 30]);
  });
});

function resizeState(edge: 'right' | 'bottom' | 'corner'): TextResizeState {
  const page = samplePage();
  return {
    page,
    block: page.text_blocks[0],
    edge,
    startClientX: 100,
    startClientY: 100,
    startBbox: [10, 10, 50, 30],
    pageBounds: new DOMRect(0, 0, 100, 100)
  };
}

function pointerEventAt(clientX: number, clientY: number): PointerEvent {
  return { clientX, clientY } as PointerEvent;
}

function samplePage(): PageData {
  return {
    page_num: 0,
    width: 200,
    height: 100,
    text_blocks: [sampleBlock()]
  };
}

function sampleBlock(): TextBlock {
  const bbox: PdfRect = [10, 10, 50, 30];
  return {
    id: 'text-block-1',
    bbox,
    originalBbox: [...bbox],
    text: 'Text', font: 'Helvetica', size: 12, color: 0,
    background_color: 16777215, originalFont: 'Helvetica', originalSize: 12,
    bold: false, italic: false, originalBold: false, originalItalic: false,
    editedText: 'Text',
    editing: false, moving: false, resizing: false,
    originalIndex: 0, inserted: false
  };
}
