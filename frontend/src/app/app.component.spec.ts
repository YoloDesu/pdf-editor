import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AppComponent, PageData } from './app.component';

describe('AppComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()]
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('should render the editor title', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('PDF Editor');
  });

  it('should collect changed text as edit payloads', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    app.pages = [pageWithEdit('Original text', 'Better text')];

    expect(app.collectPendingEdits()).toEqual([
      {
        page_num: 0,
        bbox: [10, 12, 90, 30],
        redaction_bbox: [10, 12, 90, 30],
        old_text: 'Original text',
        new_text: 'Better text',
        font: 'Helvetica',
        size: 12,
        color: 0,
        bold: false,
        italic: false,
        insert_only: false
      }
    ]);
  });

  it('should ignore unchanged text blocks', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    app.pages = [pageWithEdit('Same text', 'Same text')];

    expect(app.collectPendingEdits()).toEqual([]);
  });

  it('should send inserted text as insert-only payload', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    const page = pageWithEdit('', 'New text');
    page.text_blocks[0].inserted = true;
    app.pages = [page];

    expect(app.collectPendingEdits()[0].insert_only).toBeTrue();
  });

  it('should collect moved original text with original redaction box', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    const page = pageWithEdit('Move me', 'Move me');
    page.text_blocks[0].bbox = [20, 30, 100, 48];
    app.pages = [page];

    const edit = app.collectPendingEdits()[0];
    expect(edit.bbox).toEqual([20, 30, 100, 48]);
    expect(edit.redaction_bbox).toEqual([10, 12, 90, 30]);
  });

  it('should collect style-only changes', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    const page = pageWithEdit('Bold me', 'Bold me');
    page.text_blocks[0].bold = true;
    app.pages = [page];

    expect(app.collectPendingEdits()[0].bold).toBeTrue();
  });

  it('should preserve unchanged blocks overlapped by a nearby redaction', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    const page = pageWithOverlappingBlocks();
    page.text_blocks[0].editedText = 'First line changed';
    app.pages = [page];

    const edits = app.collectPendingEdits();

    expect(edits.length).toBe(2);
    expect(edits[1].old_text).toBe('(Nenhuma)');
    expect(edits[1].new_text).toBe('(Nenhuma)');
  });

  it('should wait until blur before previewing typed text', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    const page = pageWithEdit('Original', 'Changed');
    const block = page.text_blocks[0];
    spyOn(app, 'queuePreviewRefresh');

    app.focusTextBlock(block);
    app.queueBlockPreview(block);
    app.finishBlockEditing(page, block);

    expect(app.queuePreviewRefresh).toHaveBeenCalledOnceWith(0);
  });

  it('should wait until blur before previewing style changes', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    const page = pageWithEdit('Original', 'Original');
    const block = page.text_blocks[0];
    spyOn(app, 'queuePreviewRefresh');

    app.focusTextBlock(block);
    app.selectedBold = true;
    app.applySelectedTextStyle();
    app.finishBlockEditing(page, block);

    expect(app.queuePreviewRefresh).toHaveBeenCalledOnceWith(0);
  });

  it('should use sampled background while editing original text', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    const block = pageWithEdit('Original', 'Original').text_blocks[0];
    block.background_color = 13750737;

    app.focusTextBlock(block);

    expect(app.textBlockBackground(block)).toBe('#d1d1d1');
  });

  it('should keep inserted textboxes transparent while editing', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    const block = pageWithEdit('', 'Inserted').text_blocks[0];
    block.inserted = true;

    app.focusTextBlock(block);

    expect(app.textBlockBackground(block)).toBeNull();
  });

  it('should select a sidebar page and refresh its preview', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    const secondPage = { ...pageWithEdit('Second', 'Second'), page_num: 1 };
    spyOn(app, 'queuePreviewRefresh');
    app.pages = [pageWithEdit('First', 'First'), secondPage];

    app.selectPage(1);

    expect(app.currentPageIndex).toBe(1);
    expect(app.queuePreviewRefresh).toHaveBeenCalledOnceWith(0);
  });
});

function pageWithEdit(text: string, editedText: string): PageData {
  return {
    page_num: 0,
    width: 100,
    height: 120,
    text_blocks: [
      {
        id: 'text-block-1',
        bbox: [10, 12, 90, 30],
        originalBbox: [10, 12, 90, 30],
        text,
        font: 'Helvetica',
        size: 12,
        color: 0,
        background_color: 16777215,
        originalFont: 'Helvetica',
        originalSize: 12,
        bold: false,
        italic: false,
        originalBold: false,
        originalItalic: false,
        editedText,
        editing: false,
        moving: false,
        resizing: false,
        originalIndex: 0,
        inserted: false
      }
    ]
  };
}

function pageWithOverlappingBlocks(): PageData {
  const page = pageWithEdit('First line', 'First line');
  page.text_blocks.push({
    ...page.text_blocks[0],
    id: 'text-block-2',
    bbox: [10, 28, 90, 44],
    originalBbox: [10, 28, 90, 44],
    text: '(Nenhuma)',
    editedText: '(Nenhuma)',
    originalIndex: 1
  });
  page.text_blocks[0].bbox = [10, 12, 95, 30];
  page.text_blocks[0].originalBbox = [10, 12, 95, 30];
  return page;
}
