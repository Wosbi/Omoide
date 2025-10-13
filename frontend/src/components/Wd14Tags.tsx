import { useMemo, useState } from "react";
import { Box, Chip, Slider, Stack, Typography } from "@mui/material";

import { Media } from "../types";
import { parseWd14Tags } from "../utils/aiTags";

interface Wd14TagsProps {
  media: Media;
}

export function Wd14Tags({ media }: Readonly<Wd14TagsProps>) {
  const [minConfidence, setMinConfidence] = useState<number>(0);

  const parsedTags = useMemo(
    () =>
      parseWd14Tags(media.tags).sort((a, b) => b.score - a.score),
    [media.tags],
  );

  const filteredTags = useMemo(
    () => parsedTags.filter((tag) => tag.score * 100 >= minConfidence),
    [parsedTags, minConfidence],
  );

  const handleSliderChange = (_: Event, value: number | number[]) => {
    const nextValue = Array.isArray(value) ? value[0] : value;
    setMinConfidence(nextValue);
  };

  if (parsedTags.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No AI-generated tags were found for this media item.
      </Typography>
    );
  }

  return (
    <Box>
      <Box sx={{ maxWidth: 320, mb: 3 }}>
        <Typography variant="subtitle2" color="text.secondary" gutterBottom>
          Minimum confidence: {minConfidence}%
        </Typography>
        <Slider
          aria-label="Minimum confidence"
          value={minConfidence}
          valueLabelDisplay="auto"
          onChange={handleSliderChange}
          min={0}
          max={100}
        />
      </Box>

      {filteredTags.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No tags match the current confidence threshold.
        </Typography>
      ) : (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {filteredTags.map((tag) => {
            const percent = Math.round(tag.score * 100);
            return (
              <Chip
                key={tag.tag.id}
                label={
                  <Box component="span" sx={{ display: "flex", alignItems: "baseline", gap: 0.5 }}>
                    <Box component="span" sx={{ fontWeight: 500 }}>
                      {tag.label}
                    </Box>
                    <Box component="span" sx={{ color: "text.secondary", fontSize: "0.75rem" }}>
                      {percent}%
                    </Box>
                  </Box>
                }
                variant="outlined"
                sx={{
                  "& .MuiChip-label": {
                    display: "flex",
                    alignItems: "center",
                  },
                }}
              />
            );
          })}
        </Stack>
      )}
    </Box>
  );
}
