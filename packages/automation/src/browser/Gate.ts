/**
 * Lets a fixed number of callers through at once; the rest wait their turn.
 * Browser launches are the use: twenty starting together pin the CPU and
 * every page load times out, while a few at a time all get in.
 */
export class Gate {
  private inside = 0;
  private readonly waiting: Array<() => void> = [];

  constructor(private readonly width: number) {}

  /** Resolves once there is room; the returned function gives the place back. */
  acquire(): Promise<() => void> {
    return new Promise((resolve) => {
      const enter = (): void => {
        this.inside += 1;
        let released = false;
        resolve(() => {
          if (released) return;
          released = true;
          this.inside -= 1;
          this.waiting.shift()?.();
        });
      };
      if (this.inside < this.width) enter();
      else this.waiting.push(enter);
    });
  }
}
