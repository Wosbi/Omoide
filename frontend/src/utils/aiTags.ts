import { Tag } from "../types";

export const WD14_TAG_PREFIX = "wd14:";

export interface Wd14Tag {
  label: string;
  score: number;
  tag: Tag;
}

export function isWd14TagName(tagName: string): boolean {
  return tagName.startsWith(WD14_TAG_PREFIX);
}

export function parseWd14TagName(tagName: string): Pick<Wd14Tag, "label" | "score"> | null {
  if (!isWd14TagName(tagName)) {
    return null;
  }

  const remainder = tagName.slice(WD14_TAG_PREFIX.length);
  const [rawLabel, rawScore] = remainder.split("|");
  if (!rawLabel || !rawScore) {
    return null;
  }

  const score = Number(rawScore);
  if (Number.isNaN(score)) {
    return null;
  }

  const label = rawLabel.replace(/_/g, " ").trim();
  return { label, score };
}

export function parseWd14Tags(tags: Tag[]): Wd14Tag[] {
  return tags
    .map((tag) => {
      const parsed = parseWd14TagName(tag.name);
      if (!parsed) {
        return null;
      }

      return {
        ...parsed,
        tag,
      } as Wd14Tag;
    })
    .filter((parsedTag): parsedTag is Wd14Tag => parsedTag !== null);
}
