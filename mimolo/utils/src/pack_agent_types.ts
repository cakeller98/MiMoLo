export type ParamSpec = {
  name: string;
  type: string;
  required: boolean;
};

export type BuildManifest = {
  plugin_id: string;
  name: string;
  version: string;
  entry: string;
  files: string[];
  params?: ParamSpec[];
};

export type SourceEntry = {
  id: string;
  path: string;
  ver: string;
};

export type SourcesFile = {
  sources: SourceEntry[];
};

export type ConflictReason = "repo-newer" | "repo-exists-bump" | "hash-mismatch";

export type RepoVersion = {
  version: string;
  path: string;
};
