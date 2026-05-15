import { Component, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';

interface TextBlock {
  bbox: [number, number, number, number];
  text: string;
  font: string;
  size: number;
  color: number;
  editedText?: string;
  editing?: boolean;
  originalIndex: number;
}

interface PageData {
  page_num: number;
  width: number;
  height: number;
  text_blocks: TextBlock[];
}

interface DocumentData {
  pages: PageData[];
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent {
  title = 'PDF Editor';
  http = inject(HttpClient);
  
  apiUrl = 'http://localhost:8000';
  
  docId: string | null = null;
  pages: PageData[] = [];
  currentPageIndex = 0;
  
  uploading = false;
  saving = false;

  get currentPage(): PageData | null {
    if (this.pages.length === 0) return null;
    return this.pages[this.currentPageIndex];
  }
  
  get pageImageUrl(): string {
    if (!this.docId || !this.currentPage) return '';
    // Add timestamp to prevent caching when switching documents or reloading
    return `${this.apiUrl}/document/${this.docId}/page/${this.currentPage.page_num}/image?t=${Date.now()}`;
  }

  onFileSelected(event: Event) {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (file) {
      this.uploadPdf(file);
    }
  }

  uploadPdf(file: File) {
    this.uploading = true;
    const formData = new FormData();
    formData.append('file', file);
    
    this.http.post<{doc_id: string}>(`${this.apiUrl}/upload`, formData).subscribe({
      next: (res) => {
        this.docId = res.doc_id;
        this.fetchPages();
      },
      error: (err) => {
        console.error('Upload failed', err);
        alert('Upload failed: ' + (err.error?.detail || err.message));
        this.uploading = false;
      }
    });
  }

  fetchPages() {
    if (!this.docId) return;
    
    this.http.get<DocumentData>(`${this.apiUrl}/document/${this.docId}/pages`).subscribe({
      next: (res) => {
        this.pages = res.pages.map(page => ({
          ...page,
          text_blocks: page.text_blocks.map((b, i) => ({
            ...b,
            editedText: b.text,
            editing: false,
            originalIndex: i
          }))
        }));
        this.currentPageIndex = 0;
        this.uploading = false;
      },
      error: (err) => {
        console.error('Failed to fetch pages', err);
        alert('Failed to analyze document');
        this.uploading = false;
      }
    });
  }

  nextPage() {
    if (this.currentPageIndex < this.pages.length - 1) {
      this.currentPageIndex++;
    }
  }

  prevPage() {
    if (this.currentPageIndex > 0) {
      this.currentPageIndex--;
    }
  }

  saveDocument() {
    if (!this.docId) return;
    
    this.saving = true;
    
    const edits: any[] = [];
    for (const page of this.pages) {
      for (const block of page.text_blocks) {
        if (block.editedText !== block.text) {
          edits.push({
            page_num: page.page_num,
            bbox: block.bbox,
            old_text: block.text,
            new_text: block.editedText
          });
        }
      }
    }
    
    if (edits.length === 0) {
      alert('No changes to save.');
      this.saving = false;
      return;
    }
    
    this.http.post(`${this.apiUrl}/document/${this.docId}/save`, { edits }, { responseType: 'blob' }).subscribe({
      next: (blob) => {
        // Trigger download
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `edited_${this.docId}.pdf`;
        a.click();
        window.URL.revokeObjectURL(url);
        this.saving = false;
      },
      error: (err) => {
        console.error('Failed to save', err);
        alert('Failed to save changes');
        this.saving = false;
      }
    });
  }
}
