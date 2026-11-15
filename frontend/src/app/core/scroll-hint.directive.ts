import { Directive, ElementRef, HostListener, inject } from '@angular/core';

/** Fades the sibling swipe hint once the table has been scrolled sideways. */
@Directive({ selector: '[appScrollHint]' })
export class ScrollHint {
  private readonly host = inject(ElementRef) as ElementRef<HTMLElement>;

  @HostListener('scroll')
  onScroll(): void {
    const shell = this.host.nativeElement.parentElement;
    shell?.classList.toggle('scrolled', this.host.nativeElement.scrollLeft > 8);
  }
}
