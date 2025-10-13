import React from "react";
import { Box, Typography } from "@mui/material";
import { Media, Person, Tag } from "../types";
import config from "../config";
import TagAdder from "./TagAdder";
import { Tags } from "./Tags";
import { isWd14TagName } from "../utils/aiTags";

interface TagsSectionProps {
  media?: Media;
  person?: Person;
  onTagAdded: (tag: Tag) => void;
  onUpdate: (updatedMediaObject: Media | Person) => void;
}

export function TagsSection({
  media,
  person,
  onTagAdded,
  onUpdate,
}: TagsSectionProps) {
  const owner = media || person;
  const ownerType = media ? "media" : "person";
  const tags = owner.tags ?? [];
  const manualTags = tags.filter((tag) => !isWd14TagName(tag.name));
  const ownerId = owner.id;
  return (
    <Box mt={4}>
      {!config.READ_ONLY && (
        <Box mb={2}>
          <Typography variant="h6" gutterBottom>
            Add tag to media
          </Typography>
          <TagAdder
            ownerType={ownerType}
            ownerId={ownerId}
            existingTags={manualTags}
            onTagAdded={onTagAdded}
          />
        </Box>
      )}

      {manualTags.length > 0 && (
        <Tags media={media} person={person} onUpdate={onUpdate} />
      )}
    </Box>
  );
}
