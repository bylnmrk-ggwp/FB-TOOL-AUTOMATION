import type { RosterSource } from '@fb/application';

/**
 * A CSV pasted or uploaded into the import dialog. Quoted cells, commas
 * inside quotes and doubled quotes are handled; nothing more exotic is.
 */
export class CsvSource implements RosterSource {
  constructor(
    private readonly contents: string,
    private readonly name = 'CSV',
  ) {}

  describe(): string {
    return this.name;
  }

  async readRows(): Promise<string[][]> {
    return this.contents
      .split(/\r?\n/)
      .filter((line) => line.trim() !== '')
      .map(parseLine);
  }
}

const parseLine = (line: string): string[] => {
  const cells: string[] = [];
  let current = '';
  let quoted = false;

  for (let index = 0; index < line.length; index += 1) {
    const character = line[index] ?? '';
    if (quoted) {
      if (character === '"' && line[index + 1] === '"') {
        current += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        current += character;
      }
      continue;
    }
    if (character === '"') quoted = true;
    else if (character === ',') {
      cells.push(current);
      current = '';
    } else current += character;
  }
  cells.push(current);
  return cells;
};
