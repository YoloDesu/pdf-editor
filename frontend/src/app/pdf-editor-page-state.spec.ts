import { editablePageFromAnalysis, insertedTextBlockFromOptions } from './pdf-editor-page-state';
import { AnalyzedPageData } from './pdf-editor.models';

describe('pdf-editor-page-state', () => {
  it('should prepare analyzed blocks for editing', () => {
    const page = analyzedPage();

    const editablePage = editablePageFromAnalysis(page, () => 'block-1');

    expect(editablePage.text_blocks[0].id).toBe('block-1');
    expect(editablePage.text_blocks[0].editedText).toBe('Original');
    expect(editablePage.text_blocks[0].originalBbox).toEqual([10, 12, 90, 30]);
  });

  it('should create a transparent inserted text block', () => {
    const block = insertedTextBlockFromOptions({
      id: 'inserted-1',
      origin: { x: 20, y: 30 },
      width: 100,
      height: 24,
      font: 'Arial',
      size: 14,
      bold: true,
      italic: true,
      originalIndex: 3
    });

    expect(block.bbox).toEqual([20, 30, 120, 54]);
    expect(block.inserted).toBeTrue();
    expect(block.background_color).toBe(16777215);
  });
});

function analyzedPage(): AnalyzedPageData {
  return {
    page_num: 0,
    width: 100,
    height: 120,
    text_blocks: [{
      bbox: [10, 12, 90, 30],
      text: 'Original',
      font: 'Helvetica',
      size: 12,
      color: 0,
      background_color: 16777215,
      bold: false,
      italic: false
    }]
  };
}
