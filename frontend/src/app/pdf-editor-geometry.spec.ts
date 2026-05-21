import { textDragStateFromPointer, textResizeStateFromPointer } from './pdf-editor-geometry';
import { PageData, TextBlock } from './pdf-editor.models';

describe('pdf-editor-geometry', () => {
  it('should create drag state from a pointer event', () => {
    const event = new PointerEvent('pointerdown', { clientX: 20, clientY: 30 });
    const state = textDragStateFromPointer(event, pageElement(), pageData(), textBlock());

    expect(state.startClientX).toBe(20);
    expect(state.startClientY).toBe(30);
    expect(state.startBbox).toEqual([10, 12, 90, 30]);
  });

  it('should create resize state with the selected edge', () => {
    const event = new PointerEvent('pointerdown', { clientX: 50, clientY: 60 });
    const state = textResizeStateFromPointer(event, pageElement(), pageData(), textBlock(), 'corner');

    expect(state.edge).toBe('corner');
    expect(state.pageBounds.width).toBe(200);
  });
});

function pageElement(): HTMLElement {
  const element = document.createElement('div');
  spyOn(element, 'getBoundingClientRect').and.returnValue(new DOMRect(0, 0, 200, 240));
  return element;
}

function pageData(): PageData {
  return { page_num: 0, width: 100, height: 120, text_blocks: [] };
}

function textBlock(): TextBlock {
  return {
    id: 'block-1', bbox: [10, 12, 90, 30], originalBbox: [10, 12, 90, 30],
    text: 'Text', font: 'Helvetica', size: 12, color: 0,
    background_color: 16777215, originalFont: 'Helvetica', originalSize: 12,
    bold: false, italic: false, originalBold: false, originalItalic: false,
    editedText: 'Text', editing: false, moving: false, resizing: false,
    originalIndex: 0, inserted: false
  };
}
