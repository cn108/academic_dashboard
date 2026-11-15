import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { LessonNote, LessonResource, LessonResourcesResponse } from '../../core/models';

interface Embed {
  kind: 'iframe' | 'video';
  src: string | SafeResourceUrl;
}

@Component({
  selector: 'app-student-learning',
  imports: [DatePipe, RouterLink],
  template: `
    <div class="page-head">
      <div>
        <p class="eyebrow">Student portal</p>
        <h1>Learning hub</h1>
        <p class="muted small">
          Videos, readings and worksheets from your published lessons. Mark each one as you finish it.
        </p>
      </div>
      <a class="btn btn-ghost" routerLink="/student/dashboard">My progress</a>
    </div>

    <div class="split">
      <div class="card">
        <div class="card-head">
          <h2 style="font-size: 1rem">Lessons</h2>
          <span class="badge badge-info">{{ lessons().length }}</span>
        </div>
        @if (lessons().length) {
          <div class="grid">
            @for (lesson of lessons(); track lesson.id) {
              <button
                class="lesson-link"
                type="button"
                [class.active]="lesson.id === selectedId()"
                (click)="select(lesson)"
              >
                <span style="font-weight: 600">Week {{ lesson.week_number }} · {{ lesson.topic }}</span>
                <span class="muted small">{{ lesson.subject_name }}</span>
              </button>
            }
          </div>
        } @else {
          <p class="empty">No published lessons yet.</p>
        }
      </div>

      <div class="card">
        @if (data(); as lessonData) {
          <div class="card-head">
            <div>
              <p class="small muted">
                {{ lessonData.lesson.subject_name }} · Week {{ lessonData.lesson.week_number }}
              </p>
              <h2 style="font-size: 1.1rem">{{ lessonData.lesson.topic }}</h2>
            </div>
            <span class="badge badge-info">
              {{ completedCount() }}/{{ lessonData.resources.length }} done
            </span>
          </div>

          @if (message()) {
            <div class="alert alert-success">{{ message() }}</div>
          }
          @if (error()) {
            <div class="alert alert-error">{{ error() }}</div>
          }

          @if (lessonData.resources.length) {
            <div class="grid">
              @for (resource of lessonData.resources; track resource.id) {
                <div class="resource">
                  <div class="card-head" style="margin-bottom: 0.5rem">
                    <div>
                      <p class="small muted">{{ resource.type_label }}</p>
                      <h3 style="font-size: 0.98rem">{{ resource.title }}</h3>
                    </div>
                    @if (resource.is_completed) {
                      <span class="badge badge-success">Completed</span>
                    }
                  </div>

                  @if (resource.type === 'video' && embed(resource); as media) {
                    @if (media.kind === 'iframe') {
                      <iframe
                        class="video-frame"
                        [src]="media.src"
                        title="{{ resource.title }}"
                        loading="lazy"
                        referrerpolicy="strict-origin-when-cross-origin"
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                        allowfullscreen
                      ></iframe>
                    } @else {
                      <video class="video-frame" controls preload="metadata" [src]="media.src">
                        Your browser cannot play this video.
                      </video>
                    }
                  }

                  <div class="row-actions" style="margin-top: 0.75rem">
                    @if (resource.type === 'reading_link') {
                      <a
                        class="btn btn-ghost btn-sm"
                        [href]="resource.url"
                        target="_blank"
                        rel="noopener"
                      >
                        Open in new tab
                      </a>
                    }
                    @if (resource.type === 'document_attachment' && resource.file_url) {
                      <a
                        class="btn btn-ghost btn-sm"
                        [href]="resource.file_url"
                        target="_blank"
                        rel="noopener"
                      >
                        Download PDF
                      </a>
                    }
                    @if (!resource.is_completed) {
                      <button
                        class="btn btn-sm"
                        type="button"
                        [disabled]="busyId() === resource.id"
                        (click)="markComplete(resource)"
                      >
                        {{ busyId() === resource.id ? 'Saving…' : 'Mark as complete' }}
                      </button>
                    } @else {
                      <span class="small muted">
                        Completed {{ resource.completed_at | date: 'mediumDate' }}
                      </span>
                    }
                  </div>
                </div>
              }
            </div>
          } @else {
            <p class="empty">No extra resources for this lesson.</p>
          }
        } @else {
          <p class="empty">Choose a lesson to see its resources.</p>
        }
      </div>
    </div>
  `,
})
export class StudentLearning {
  private readonly api = inject(ApiService);
  private readonly sanitizer = inject(DomSanitizer);

  readonly lessons = signal<LessonNote[]>([]);
  readonly selectedId = signal<number | null>(null);
  readonly data = signal<LessonResourcesResponse | null>(null);
  readonly embeds = signal(new Map<number, Embed>());
  readonly busyId = signal<number | null>(null);
  readonly message = signal('');
  readonly error = signal('');

  readonly completedCount = computed(
    () => this.data()?.resources.filter((row) => row.is_completed).length ?? 0,
  );

  constructor() {
    this.api.list<LessonNote>('lesson-notes').subscribe({
      next: (rows) => {
        const ordered = rows.slice().reverse();
        this.lessons.set(ordered);
        if (ordered.length) {
          this.select(ordered[0]);
        }
      },
      error: () => this.error.set('Could not load your lessons.'),
    });
  }

  select(lesson: LessonNote): void {
    this.selectedId.set(lesson.id);
    this.message.set('');
    this.error.set('');
    this.api.get<LessonResourcesResponse>(`lessons/${lesson.id}/resources`).subscribe({
      next: (data) => {
        const embeds = new Map<number, Embed>();
        for (const resource of data.resources) {
          const media = this.mediaFor(resource);
          if (media) {
            embeds.set(resource.id, media);
          }
        }
        this.embeds.set(embeds);
        this.data.set(data);
      },
      error: () => {
        this.data.set(null);
        this.error.set('Could not load the resources for that lesson.');
      },
    });
  }

  embed(resource: LessonResource): Embed | null {
    return this.embeds().get(resource.id) ?? null;
  }

  markComplete(resource: LessonResource): void {
    this.busyId.set(resource.id);
    this.error.set('');
    this.message.set('');
    this.setCompleted(resource.id, true);

    this.api
      .action<{ completed_at: string }>(`resources/${resource.id}/complete`)
      .subscribe({
        next: (result) => {
          this.busyId.set(null);
          this.setCompleted(resource.id, true, result.completed_at);
          this.message.set(`Marked “${resource.title}” complete.`);
        },
        error: () => {
          this.busyId.set(null);
          this.setCompleted(resource.id, false);
          this.error.set('Could not save that just now. Try again.');
        },
      });
  }

  private setCompleted(id: number, completed: boolean, completedAt: string | null = null): void {
    const data = this.data();
    if (!data) {
      return;
    }
    this.data.set({
      ...data,
      resources: data.resources.map((row) =>
        row.id === id
          ? { ...row, is_completed: completed, completed_at: completedAt ?? row.completed_at }
          : row,
      ),
    });
  }

  private mediaFor(resource: LessonResource): Embed | null {
    if (resource.type !== 'video' || !resource.url) {
      return null;
    }
    const youtube = resource.url.match(
      /(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)([\w-]{6,})/,
    );
    if (youtube) {
      return {
        kind: 'iframe',
        src: this.sanitizer.bypassSecurityTrustResourceUrl(
          `https://www.youtube.com/embed/${youtube[1]}`,
        ),
      };
    }
    const vimeo = resource.url.match(/vimeo\.com\/(\d+)/);
    if (vimeo) {
      return {
        kind: 'iframe',
        src: this.sanitizer.bypassSecurityTrustResourceUrl(
          `https://player.vimeo.com/video/${vimeo[1]}`,
        ),
      };
    }
    return { kind: 'video', src: resource.url };
  }
}
